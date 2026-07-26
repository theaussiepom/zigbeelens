"""Real Home Assistant registry/manager control process for the live E2E test."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from datetime import timedelta
import importlib
from importlib.metadata import version as distribution_version
import inspect
import json
import logging
from pathlib import Path
import re
import signal
import socket
import sys
from types import SimpleNamespace
from typing import Any

from aiohttp import ClientSession, web
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame

IEEE = "0x00124b0024abcd01"
INTEGRATION_VERSION = "0.1.14"
PUBLISH_TIMEOUT_SECONDS = 5
THREAD_SAFETY_MARKERS = (
    "from a thread other than the event loop",
    "non-thread-safe operation invoked on an event loop",
)
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


class _ObservedApiClient:
    """Observe completed production Core publishes without scheduling manager work."""

    def __init__(self, delegate: Any, hass: HomeAssistant) -> None:
        self._delegate = delegate
        self._hass = hass
        self._publish_count = 0
        self._publish_changed = asyncio.Condition()

    @property
    def publish_count(self) -> int:
        return self._publish_count

    async def async_get_device_inventory(self) -> Any:
        return await self._delegate.async_get_device_inventory()

    async def async_publish_home_assistant_enrichment(
        self,
        devices: tuple[Any, ...],
    ) -> Any:
        if asyncio.get_running_loop() is not self._hass.loop:
            raise RuntimeError("Core publish did not run on the Home Assistant loop")
        result = await self._delegate.async_publish_home_assistant_enrichment(
            devices
        )
        async with self._publish_changed:
            self._publish_count += 1
            self._publish_changed.notify_all()
        return result

    async def async_wait_for_publish_count(self, expected: int) -> None:
        async def wait_for_count() -> None:
            async with self._publish_changed:
                await self._publish_changed.wait_for(
                    lambda: self._publish_count >= expected
                )

        await asyncio.wait_for(
            wait_for_count(),
            timeout=PUBLISH_TIMEOUT_SECONDS,
        )


class _RuntimeErrorCapture(logging.Handler):
    """Retain error logs and thread-safety reports for a fail-closed exit."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        lowered = message.lower()
        if record.levelno >= logging.ERROR or any(
            marker in lowered for marker in THREAD_SAFETY_MARKERS
        ):
            self.messages.append(message)

    def raise_if_any(self, loop_errors: list[dict[str, Any]]) -> None:
        if self.messages or loop_errors:
            raise RuntimeError(
                "Home Assistant logged an error or reported an event-loop exception"
            )


async def _load_registries(hass: HomeAssistant) -> None:
    await ar.async_load(hass)
    setup_device_registry = getattr(dr, "async_setup", None)
    if setup_device_registry is not None:
        setup_device_registry(hass)
    await dr.async_load(hass)
    await er.async_load(hass)


async def _serve(args: argparse.Namespace) -> None:
    args.config_dir.mkdir(parents=True, exist_ok=True)
    expected_components = (args.config_dir / "custom_components").resolve()
    if args.components_dir.resolve() != expected_components:
        raise RuntimeError(
            "Home Assistant components are not in the disposable config directory"
        )
    if re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is None:
        raise RuntimeError("staged source commit is invalid")
    staged_source_commit = (args.config_dir / "SOURCE_COMMIT").read_text(
        encoding="utf-8"
    )
    if staged_source_commit != f"{args.source_commit}\n":
        raise RuntimeError("disposable integration provenance does not match")

    args.version_file.write_text(
        (
            f"{sys.version_info.major}.{sys.version_info.minor}|"
            f"{distribution_version('homeassistant')}\n"
        ),
        encoding="utf-8",
    )
    hass = HomeAssistant(str(args.config_dir))
    hass.loop.set_debug(True)
    loader.async_setup(hass)
    setup_frame = getattr(frame, "async_setup", None)
    if setup_frame is not None:
        setup_frame(hass)

    runtime_errors = _RuntimeErrorCapture()
    root_logger = logging.getLogger()
    root_logger.addHandler(runtime_errors)
    loop_errors: list[dict[str, Any]] = []
    previous_exception_handler = hass.loop.get_exception_handler()

    def capture_loop_error(
        loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        loop_errors.append(dict(context))
        if previous_exception_handler is not None:
            previous_exception_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    hass.loop.set_exception_handler(capture_loop_error)

    integration = await loader.async_get_integration(hass, "zigbeelens")
    manager_module = importlib.import_module(
        f"{integration.pkg_path}.enrichment_manager"
    )
    api_module = importlib.import_module(f"{integration.pkg_path}.api")
    compatibility_module = importlib.import_module(
        f"{integration.pkg_path}.compatibility"
    )
    HomeAssistantEnrichmentManager = (
        manager_module.HomeAssistantEnrichmentManager
    )
    ZigbeeLensApiClient = api_module.ZigbeeLensApiClient
    EnrichmentContractState = compatibility_module.EnrichmentContractState
    loaded_component = Path(
        inspect.getfile(HomeAssistantEnrichmentManager)
    ).resolve().parent
    expected_component = (args.components_dir / "zigbeelens").resolve()
    if loaded_component != expected_component:
        raise RuntimeError("Home Assistant loaded a non-staged integration")
    if integration.version != INTEGRATION_VERSION:
        raise RuntimeError("staged integration version is not 0.1.14")
    args.provenance_file.write_text(
        f"{args.source_commit}|{integration.version}\n",
        encoding="utf-8",
    )

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
    client = _ObservedApiClient(
        ZigbeeLensApiClient(session, args.core_url),
        hass,
    )
    entry = _ManagerEntry()
    manager = HomeAssistantEnrichmentManager(
        hass,
        entry,
        client,
        capability_provider=lambda: EnrichmentContractState.SUPPORTED,
        debounce_seconds=0.1,
        reconciliation_interval=timedelta(days=1),
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
        expected_publish_count = client.publish_count + 1
        device = device_registry.async_update_device(
            device.id,
            name_by_user=name,
            area_id=areas[area_key].id if area_key is not None else None,
        )
        if not manager_started:
            await manager.async_start()
            manager_started = True
        else:
            # The official registry event owns the production later scheduler
            # and task factory. The completed Core publish is the wait seam.
            await client.async_wait_for_publish_count(expected_publish_count)
        runtime_errors.raise_if_any(loop_errors)
        if client.publish_count != expected_publish_count:
            raise web.HTTPInternalServerError(
                text="unexpected enrichment publish count"
            )
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
        try:
            await manager.async_stop()
            await session.close()
            await runner.cleanup()
            await hass.async_stop(force=True)
            runtime_errors.raise_if_any(loop_errors)
        finally:
            hass.loop.set_exception_handler(previous_exception_handler)
            root_logger.removeHandler(runtime_errors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-url", required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--components-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--url-file", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, required=True)
    parser.add_argument("--provenance-file", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_serve(args))


if __name__ == "__main__":
    main()
