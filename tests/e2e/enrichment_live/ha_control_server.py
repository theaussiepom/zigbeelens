"""Real Home Assistant registry/manager control process for the live E2E test."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version as distribution_version
import json
from pathlib import Path
import signal
import socket
import sys
from types import SimpleNamespace
from typing import Any

from aiohttp import ClientSession, web
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = REPOSITORY_ROOT / "apps" / "ha_integration" / "custom_components"
sys.path.insert(0, str(COMPONENTS))

from zigbeelens.api import ZigbeeLensApiClient  # noqa: E402
from zigbeelens.compatibility import EnrichmentContractState  # noqa: E402
from zigbeelens.enrichment_manager import HomeAssistantEnrichmentManager  # noqa: E402

IEEE = "0x00124b0024abcd01"
STATES: dict[str, tuple[str | None, str | None]] = {
    "initial": ("HA Kitchen Lamp", "kitchen"),
    "renamed": ("HA Study Lamp", "study"),
    "removed": (None, None),
}


class _ManagerEntry:
    def __init__(self) -> None:
        self.unload_callbacks: list[Callable[[], Any]] = []
        self.reauth_calls = 0

    def async_on_unload(self, callback: Callable[[], Any]) -> None:
        self.unload_callbacks.append(callback)

    def async_start_reauth(
        self,
        _hass: HomeAssistant,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        del data
        self.reauth_calls += 1


@dataclass
class _ScheduledAction:
    action: Callable[[], None]
    cancelled: bool = False


class _ManualDebounce:
    """Deterministically drain the real manager's registry-event debounce."""

    def __init__(self) -> None:
        self._actions: list[_ScheduledAction] = []

    def schedule(
        self,
        _delay: float,
        action: Callable[[], None],
    ) -> Callable[[], None]:
        scheduled = _ScheduledAction(action)
        self._actions.append(scheduled)

        def cancel() -> None:
            scheduled.cancelled = True

        return cancel

    def drain_one(self) -> None:
        pending = [item for item in self._actions if not item.cancelled]
        self._actions.clear()
        if len(pending) != 1:
            raise RuntimeError(
                f"expected one coalesced registry debounce, got {len(pending)}"
            )
        pending[0].action()


async def _load_registries(hass: HomeAssistant) -> None:
    await ar.async_load(hass)
    setup_device_registry = getattr(dr, "async_setup", None)
    if setup_device_registry is not None:
        setup_device_registry(hass)
    await dr.async_load(hass)
    await er.async_load(hass)


async def _serve(args: argparse.Namespace) -> None:
    args.config_dir.mkdir(parents=True, exist_ok=True)
    args.version_file.write_text(
        (
            f"{sys.version_info.major}.{sys.version_info.minor}|"
            f"{distribution_version('homeassistant')}\n"
        ),
        encoding="utf-8",
    )
    hass = HomeAssistant(str(args.config_dir))
    config_entry = SimpleNamespace(domain="mqtt", title="", disabled_by=None)
    hass.config_entries = SimpleNamespace(
        async_get_entry=lambda _entry_id: config_entry
    )
    await _load_registries(hass)

    area_registry = ar.async_get(hass)
    areas = {
        "kitchen": area_registry.async_create("Kitchen"),
        "study": area_registry.async_create("Study"),
    }
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id="e2e-entry",
        connections={(dr.CONNECTION_ZIGBEE, IEEE)},
        name="",
    )
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "light",
        "zigbee2mqtt",
        "e2e-lamp",
        device_id=device.id,
        suggested_object_id="e2e_lamp",
    )

    session = ClientSession()
    client = ZigbeeLensApiClient(session, args.core_url)
    entry = _ManagerEntry()
    debounce = _ManualDebounce()
    manager = HomeAssistantEnrichmentManager(
        hass,
        entry,
        client,
        capability_provider=lambda: EnrichmentContractState.SUPPORTED,
        later_scheduler=debounce.schedule,
        interval_scheduler=lambda _interval, _action: lambda: None,
    )
    manager_started = False

    async def apply_state(request: web.Request) -> web.Response:
        nonlocal device, manager_started
        try:
            payload = await request.json()
        except (json.JSONDecodeError, TypeError):
            raise web.HTTPBadRequest(text="expected JSON state") from None
        state = payload.get("state") if isinstance(payload, dict) else None
        if state not in STATES:
            raise web.HTTPBadRequest(text="unknown state")
        name, area_key = STATES[state]
        device = device_registry.async_update_device(
            device.id,
            name_by_user=name,
            area_id=areas[area_key].id if area_key is not None else None,
        )
        if not manager_started:
            await manager.async_start()
            manager_started = True
        else:
            # The official registry update fires the real HA bus event. Drain
            # its injected debounce queue, then wait on the manager's bounded
            # task seam instead of sleeping or calling reconcile directly.
            await hass.async_block_till_done()
            debounce.drain_one()
            await manager.async_wait_for_idle()
        diagnostics = manager.diagnostics
        if (
            diagnostics["sync_state"] != "successful"
            or diagnostics["matched"] != 1
            or diagnostics["stored"] != 1
        ):
            raise web.HTTPInternalServerError(
                text=json.dumps({"diagnostics": diagnostics}, sort_keys=True)
            )
        return web.json_response(
            {
                "state": state,
                "ha_device_id": device.id,
                "diagnostics": diagnostics,
            }
        )

    application = web.Application()
    application.router.add_get("/health", lambda _request: web.json_response({"ok": True}))
    application.router.add_post("/apply", apply_state)
    runner = web.AppRunner(application, access_log=None)
    await runner.setup()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    listener.setblocking(False)
    site = web.SockSite(runner, listener)
    await site.start()
    port = listener.getsockname()[1]
    args.url_file.write_text(f"http://127.0.0.1:{port}\n", encoding="utf-8")

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    try:
        await stopped.wait()
    finally:
        await manager.async_stop()
        await session.close()
        await runner.cleanup()
        await hass.async_stop(force=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-url", required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--url-file", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_serve(args))


if __name__ == "__main__":
    main()
