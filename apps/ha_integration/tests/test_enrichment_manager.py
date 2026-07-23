"""Lifecycle, complete-snapshot, retry, and cleanup tests for enrichment."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from zigbeelens.api import HomeAssistantEnrichmentResult
from zigbeelens.compatibility import EnrichmentContractState
from zigbeelens.enrichment_manager import (
    EnrichmentSyncState,
    HomeAssistantEnrichmentManager,
)
from zigbeelens.exceptions import (
    ZigbeeLensAuthError,
    ZigbeeLensConnectionError,
    ZigbeeLensInvalidResponseError,
    ZigbeeLensRequestRejectedError,
)
from zigbeelens.ha_enrichment import (
    CoreInventoryDevice,
    CoreInventorySnapshot,
    HomeAssistantRegistrySnapshot,
    RegistryCandidate,
    RegistrySnapshotState,
)

IEEE = "0x00124b0001abcdef"


@dataclass
class ScheduledAction:
    when: object
    action: object
    cancelled: bool = False
    fired: bool = False


class FakeScheduler:
    def __init__(self):
        self.handles: list[ScheduledAction] = []

    def schedule(self, when, action):
        handle = ScheduledAction(when, action)
        self.handles.append(handle)

        def cancel():
            handle.cancelled = True

        return cancel

    def pending(self) -> list[ScheduledAction]:
        return [
            handle
            for handle in self.handles
            if not handle.cancelled and not handle.fired
        ]

    def fire(self, handle: ScheduledAction):
        assert not handle.cancelled
        assert not handle.fired
        handle.fired = True
        handle.action()


class FakeBus:
    def __init__(self):
        self.listeners: dict[str, list[dict[str, object]]] = {}

    def async_listen(self, event_type, listener):
        registration = {"listener": listener, "active": True}
        self.listeners.setdefault(event_type, []).append(registration)

        def cancel():
            registration["active"] = False

        return cancel

    def fire(self, event_type, data=None):
        for registration in list(self.listeners.get(event_type, [])):
            if registration["active"]:
                registration["listener"](SimpleNamespace(data=data))

    @property
    def active_count(self) -> int:
        return sum(
            bool(registration["active"])
            for registrations in self.listeners.values()
            for registration in registrations
        )


class FakeEntry:
    def __init__(self):
        self.unload_callbacks = []
        self.reauth_calls = 0

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)

    def async_start_reauth(self, hass, **kwargs):
        self.reauth_calls += 1

    async def async_run_unload(self):
        while self.unload_callbacks:
            result = self.unload_callbacks.pop()()
            if result is not None:
                await result


class MutableRegistrySource:
    def __init__(self, snapshot: HomeAssistantRegistrySnapshot):
        self.snapshot = snapshot
        self.calls = 0

    def __call__(self, hass):
        self.calls += 1
        return self.snapshot


class FakeClient:
    def __init__(
        self,
        inventory: CoreInventorySnapshot,
        *,
        inventory_outcomes=None,
        publish_outcomes=None,
    ):
        self.inventory = inventory
        self.inventory_outcomes = list(inventory_outcomes or [])
        self.publish_outcomes = list(publish_outcomes or [])
        self.inventory_calls = 0
        self.published = []
        self.accepted = "prior-accepted-snapshot"
        self.active_publish = 0
        self.max_active_publish = 0
        self.block_on_call: int | None = None
        self.publish_entered = asyncio.Event()
        self.publish_release = asyncio.Event()

    async def async_get_device_inventory(self):
        self.inventory_calls += 1
        if self.inventory_outcomes:
            outcome = self.inventory_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return self.inventory

    async def async_publish_home_assistant_enrichment(self, devices):
        self.published.append(devices)
        call_number = len(self.published)
        self.active_publish += 1
        self.max_active_publish = max(
            self.max_active_publish,
            self.active_publish,
        )
        try:
            if self.block_on_call == call_number:
                self.publish_entered.set()
                await self.publish_release.wait()
            if self.publish_outcomes:
                outcome = self.publish_outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                result = outcome
            else:
                result = _result(len(devices))
            self.accepted = devices
            return result
        finally:
            self.active_publish -= 1


def _result(submitted: int) -> HomeAssistantEnrichmentResult:
    return HomeAssistantEnrichmentResult(
        home_assistant_enrichment_contract_version=1,
        submitted=submitted,
        matched=submitted,
        unmatched=0,
        ambiguous=0,
        stored=submitted,
        last_push_at="2026-07-23T12:00:00+00:00",
    )


def _registry(
    *,
    name: str = "Reading Lamp",
    state: RegistrySnapshotState = RegistrySnapshotState.COMPLETE,
) -> HomeAssistantRegistrySnapshot:
    if state is RegistrySnapshotState.UNAVAILABLE:
        return HomeAssistantRegistrySnapshot(state)
    return HomeAssistantRegistrySnapshot(
        state,
        (
            RegistryCandidate(
                ieee_address=IEEE,
                ha_device_id="ha-device-id",
                ha_device_name=name,
                area_id="living",
                area_name="Living Room",
                entity_id="light.reading_lamp",
                original_name="source-lamp",
            ),
        ),
    )


def _inventory(network_id: str = "home") -> CoreInventorySnapshot:
    return CoreInventorySnapshot(
        (CoreInventoryDevice(network_id, IEEE, "source-lamp"),)
    )


def _manager(
    source: MutableRegistrySource,
    client: FakeClient,
    *,
    contract_state: EnrichmentContractState = EnrichmentContractState.SUPPORTED,
):
    bus = FakeBus()
    hass = SimpleNamespace(bus=bus)
    entry = FakeEntry()
    later = FakeScheduler()
    interval = FakeScheduler()
    manager = HomeAssistantEnrichmentManager(
        hass,
        entry,
        client,
        capability_provider=lambda: contract_state,
        registry_builder=source,
        later_scheduler=later.schedule,
        interval_scheduler=interval.schedule,
        task_factory=asyncio.create_task,
        now=lambda: "2026-07-23T12:00:01+00:00",
        debounce_seconds=2,
        retry_delays=(5, 10),
    )
    return manager, bus, entry, later, interval


@pytest.mark.asyncio
async def test_initial_sync_registers_exact_listeners_and_posts_complete_snapshot():
    source = MutableRegistrySource(_registry())
    client = FakeClient(_inventory())
    manager, bus, entry, later, interval = _manager(source, client)

    await manager.async_start()

    assert list(bus.listeners) == [
        dr.EVENT_DEVICE_REGISTRY_UPDATED,
        er.EVENT_ENTITY_REGISTRY_UPDATED,
        ar.EVENT_AREA_REGISTRY_UPDATED,
    ]
    assert bus.active_count == 3
    assert len(entry.unload_callbacks) == 1
    assert len(interval.pending()) == 1
    assert later.pending() == []
    assert len(client.published) == 1
    assert client.published[0][0].network_id == "home"
    assert manager.diagnostics == {
        "sync_state": "successful",
        "last_attempt_at": "2026-07-23T12:00:01+00:00",
        "last_success_at": "2026-07-23T12:00:00+00:00",
        "submitted": 1,
        "matched": 1,
        "unmatched": 0,
        "ambiguous": 0,
        "stored": 1,
        "failure_reason": None,
    }
    await manager.async_stop()


@pytest.mark.parametrize(
    "registry",
    [
        HomeAssistantRegistrySnapshot(RegistrySnapshotState.COMPLETE),
        _registry(),
    ],
)
@pytest.mark.asyncio
async def test_complete_empty_or_zero_match_may_post_empty(registry):
    source = MutableRegistrySource(registry)
    client = FakeClient(CoreInventorySnapshot(()))
    manager, _bus, _entry, _later, _interval = _manager(source, client)

    await manager.async_start()

    assert client.published == [()]
    diagnostics = manager.diagnostics
    assert diagnostics["sync_state"] == "successful"
    assert diagnostics["stored"] == 0
    if registry.candidates:
        assert diagnostics["submitted"] == 1
        assert diagnostics["unmatched"] == 1
    else:
        assert diagnostics["submitted"] == 0
        assert diagnostics["unmatched"] == 0
    await manager.async_stop()


@pytest.mark.asyncio
async def test_unavailable_registry_never_fetches_inventory_or_posts_empty():
    source = MutableRegistrySource(_registry(state=RegistrySnapshotState.UNAVAILABLE))
    client = FakeClient(_inventory())
    manager, _bus, _entry, later, _interval = _manager(source, client)

    await manager.async_start()

    assert client.inventory_calls == 0
    assert client.published == []
    assert [handle.when for handle in later.pending()] == [5]
    assert manager.diagnostics["sync_state"] == "failed_source_unavailable"
    assert manager.diagnostics["submitted"] is None
    await manager.async_stop()


@pytest.mark.parametrize(
    ("failure", "expected_state", "retry"),
    [
        (
            ZigbeeLensConnectionError("inventory offline"),
            EnrichmentSyncState.INVENTORY_UNAVAILABLE.value,
            True,
        ),
        (
            ZigbeeLensInvalidResponseError("partial inventory"),
            EnrichmentSyncState.INVALID_RESPONSE.value,
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_incomplete_inventory_never_posts_replacement(
    failure,
    expected_state,
    retry,
):
    source = MutableRegistrySource(_registry())
    client = FakeClient(_inventory(), inventory_outcomes=[failure])
    manager, _bus, _entry, later, _interval = _manager(source, client)

    await manager.async_start()

    assert client.published == []
    assert client.accepted == "prior-accepted-snapshot"
    assert manager.diagnostics["sync_state"] == expected_state
    assert bool(later.pending()) is retry
    await manager.async_stop()


@pytest.mark.parametrize(
    ("contract", "expected_state", "retry"),
    [
        (
            EnrichmentContractState.UNSUPPORTED,
            "contract_unsupported",
            False,
        ),
        (EnrichmentContractState.MISSING, "contract_missing", False),
        (EnrichmentContractState.MALFORMED, "contract_malformed", False),
        (
            EnrichmentContractState.UNAVAILABLE,
            "failed_contract_unavailable",
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_capability_states_are_distinct_and_fail_closed(
    contract,
    expected_state,
    retry,
):
    source = MutableRegistrySource(_registry())
    client = FakeClient(_inventory())
    manager, _bus, _entry, later, _interval = _manager(
        source,
        client,
        contract_state=contract,
    )

    await manager.async_start()

    assert source.calls == 0
    assert client.inventory_calls == 0
    assert client.published == []
    assert manager.diagnostics["sync_state"] == expected_state
    assert bool(later.pending()) is retry
    await manager.async_stop()


@pytest.mark.asyncio
async def test_registry_burst_is_debounced_and_unchanged_payload_is_not_reposted():
    source = MutableRegistrySource(_registry(name="First Name"))
    client = FakeClient(_inventory())
    manager, bus, _entry, later, _interval = _manager(source, client)
    await manager.async_start()

    source.snapshot = _registry(name="Changed Name")
    bus.fire(dr.EVENT_DEVICE_REGISTRY_UPDATED, {"action": "update"})
    bus.fire(er.EVENT_ENTITY_REGISTRY_UPDATED, {"action": "create"})
    bus.fire(ar.EVENT_AREA_REGISTRY_UPDATED, {"action": "remove"})

    assert len(later.handles) == 3
    assert len(later.pending()) == 1
    later.fire(later.pending()[0])
    await manager.async_wait_for_idle()
    assert len(client.published) == 2
    assert client.published[-1][0].ha_device_name == "Changed Name"

    manager.async_request_sync()
    later.fire(later.pending()[0])
    await manager.async_wait_for_idle()
    assert len(client.published) == 2
    assert manager.diagnostics["sync_state"] == "successful"
    await manager.async_stop()


@pytest.mark.asyncio
async def test_core_inventory_change_changes_exact_network_and_republishes():
    source = MutableRegistrySource(_registry())
    client = FakeClient(
        _inventory("network-a"),
        inventory_outcomes=[
            _inventory("network-a"),
            _inventory("network-b"),
        ],
    )
    manager, _bus, _entry, later, _interval = _manager(source, client)
    await manager.async_start()

    manager.async_request_sync()
    later.fire(later.pending()[0])
    await manager.async_wait_for_idle()

    assert [published[0].network_id for published in client.published] == [
        "network-a",
        "network-b",
    ]
    await manager.async_stop()


@pytest.mark.asyncio
async def test_periodic_reconciliation_forces_republish_for_core_restart_recovery():
    source = MutableRegistrySource(_registry())
    client = FakeClient(_inventory())
    manager, _bus, _entry, _later, interval = _manager(source, client)
    await manager.async_start()

    interval.fire(interval.pending()[0])
    await manager.async_wait_for_idle()

    assert len(client.published) == 2
    await manager.async_stop()


@pytest.mark.asyncio
async def test_transient_publish_failure_retries_without_clearing_or_duplication():
    source = MutableRegistrySource(_registry())
    client = FakeClient(
        _inventory(),
        publish_outcomes=[ZigbeeLensConnectionError("offline")],
    )
    manager, bus, _entry, later, _interval = _manager(source, client)

    await manager.async_start()
    assert client.accepted == "prior-accepted-snapshot"
    assert manager.diagnostics["sync_state"] == "failed_connection"
    assert [handle.when for handle in later.pending()] == [5]

    later.fire(later.pending()[0])
    await manager.async_wait_for_idle()

    assert len(client.published) == 2
    assert client.accepted == client.published[-1]
    assert client.max_active_publish == 1
    assert bus.active_count == 3
    assert manager.diagnostics["sync_state"] == "successful"
    assert later.pending() == []
    await manager.async_stop()


@pytest.mark.asyncio
async def test_rate_limit_is_retried_but_other_payload_rejections_are_not():
    source = MutableRegistrySource(_registry())
    client = FakeClient(
        _inventory(),
        publish_outcomes=[ZigbeeLensRequestRejectedError(429, "rate_limited")],
    )
    manager, _bus, _entry, later, _interval = _manager(source, client)

    await manager.async_start()
    assert manager.diagnostics["failure_reason"] == "rate_limited"
    assert [handle.when for handle in later.pending()] == [5]

    later.fire(later.pending()[0])
    await manager.async_wait_for_idle()

    assert len(client.published) == 2
    assert manager.diagnostics["sync_state"] == "successful"
    await manager.async_stop()


@pytest.mark.asyncio
async def test_retry_backoff_is_capped_and_success_clears_pending_retry():
    source = MutableRegistrySource(_registry())
    client = FakeClient(
        _inventory(),
        publish_outcomes=[
            ZigbeeLensConnectionError("first"),
            ZigbeeLensConnectionError("second"),
            ZigbeeLensConnectionError("third"),
        ],
    )
    manager, _bus, _entry, later, _interval = _manager(source, client)

    await manager.async_start()
    observed_delays = []
    for _ in range(3):
        retry = later.pending()[0]
        observed_delays.append(retry.when)
        later.fire(retry)
        await manager.async_wait_for_idle()

    assert observed_delays == [5, 10, 10]
    assert manager.diagnostics["sync_state"] == "successful"
    assert later.pending() == []
    await manager.async_stop()


@pytest.mark.asyncio
async def test_authentication_failure_starts_linked_reauth_once():
    source = MutableRegistrySource(_registry())
    client = FakeClient(
        _inventory(),
        inventory_outcomes=[
            ZigbeeLensAuthError("secret one"),
            ZigbeeLensAuthError("secret two"),
        ],
    )
    manager, _bus, entry, later, _interval = _manager(source, client)

    await manager.async_start()
    await manager.async_reconcile(force=True)

    assert entry.reauth_calls == 1
    assert client.published == []
    assert later.pending() == []
    assert manager.diagnostics["sync_state"] == "failed_authentication"
    await manager.async_stop()


@pytest.mark.asyncio
async def test_payload_rejection_is_terminal_and_retains_prior_acceptance():
    source = MutableRegistrySource(_registry())
    client = FakeClient(
        _inventory(),
        publish_outcomes=[ZigbeeLensRequestRejectedError(422, "validation")],
    )
    manager, _bus, _entry, later, interval = _manager(source, client)

    await manager.async_start()

    assert client.accepted == "prior-accepted-snapshot"
    assert later.pending() == []
    assert manager.diagnostics["sync_state"] == "failed_request_rejected"
    assert manager.diagnostics["failure_reason"] == "validation"

    # Ordinary coordinator/registry notifications may re-read inventory, but a
    # terminal rejection of the identical payload is not POSTed every poll.
    manager.async_request_sync()
    later.fire(later.pending()[0])
    await manager.async_wait_for_idle()
    assert len(client.published) == 1

    # Bounded periodic reconciliation is forced so a repaired Core route can
    # recover even when the payload itself did not change.
    interval.fire(interval.pending()[0])
    await manager.async_wait_for_idle()
    assert len(client.published) == 2
    assert manager.diagnostics["sync_state"] == "successful"
    await manager.async_stop()


@pytest.mark.asyncio
async def test_missing_exact_post_route_becomes_contract_unsupported():
    source = MutableRegistrySource(_registry())
    client = FakeClient(
        _inventory(),
        publish_outcomes=[ZigbeeLensRequestRejectedError(404, "not_found")],
    )
    manager, _bus, _entry, later, _interval = _manager(source, client)

    await manager.async_start()

    assert client.accepted == "prior-accepted-snapshot"
    assert later.pending() == []
    assert manager.diagnostics["sync_state"] == "failed_contract_unsupported"
    assert manager.diagnostics["failure_reason"] == "not_found"
    await manager.async_stop()


@pytest.mark.asyncio
async def test_normal_reload_never_clears_and_failed_new_sync_preserves_acceptance():
    source = MutableRegistrySource(_registry(name="Accepted Name"))
    client = FakeClient(_inventory())
    first, first_bus, _entry, _later, _interval = _manager(source, client)
    await first.async_start()
    accepted_before_reload = client.accepted
    await first.async_stop()
    assert first_bus.active_count == 0

    source.snapshot = _registry(name="Changed During Reload")
    client.publish_outcomes.append(ZigbeeLensConnectionError("transient"))
    second, second_bus, _entry, _later, _interval = _manager(source, client)
    await second.async_start()

    assert second_bus.active_count == 3
    assert client.accepted == accepted_before_reload
    assert second.diagnostics["sync_state"] == "failed_connection"
    await second.async_stop()


@pytest.mark.asyncio
async def test_concurrent_requests_coalesce_and_never_overlap_posts():
    source = MutableRegistrySource(_registry())
    client = FakeClient(_inventory())
    client.block_on_call = 1
    manager, _bus, _entry, _later, _interval = _manager(source, client)

    first = asyncio.create_task(manager.async_reconcile(force=True))
    await client.publish_entered.wait()
    await manager.async_reconcile(force=True)
    client.publish_release.set()
    await first

    assert client.inventory_calls == 2
    assert len(client.published) == 2
    assert client.max_active_publish == 1
    await manager.async_stop()


@pytest.mark.asyncio
async def test_config_entry_unload_cancels_all_owned_resources_and_inflight_work():
    source = MutableRegistrySource(_registry(name="Initial"))
    client = FakeClient(_inventory())
    manager, bus, entry, later, interval = _manager(source, client)
    await manager.async_start()

    source.snapshot = _registry(name="Changed")
    client.block_on_call = 2
    manager.async_request_sync()
    debounce = later.pending()[0]
    later.fire(debounce)
    await client.publish_entered.wait()

    await entry.async_run_unload()

    assert bus.active_count == 0
    assert all(handle.cancelled or handle.fired for handle in later.handles)
    assert all(handle.cancelled or handle.fired for handle in interval.handles)
    assert client.active_publish == 0
    assert client.accepted == client.published[0]

    scheduled_before = len(later.handles)
    bus.fire(dr.EVENT_DEVICE_REGISTRY_UPDATED, {"different": "shape"})
    manager.async_request_sync()
    assert len(later.handles) == scheduled_before


@pytest.mark.asyncio
async def test_manager_diagnostics_are_identity_free_and_categorical():
    sensitive_name = "name-secret-sentinel"
    source = MutableRegistrySource(_registry(name=sensitive_name))
    client = FakeClient(
        _inventory(),
        publish_outcomes=[ZigbeeLensRequestRejectedError(409, "conflict")],
    )
    manager, _bus, _entry, _later, _interval = _manager(source, client)
    await manager.async_start()

    encoded = repr(manager.diagnostics)
    for secret in (
        sensitive_name,
        "Living Room",
        "living",
        "light.reading_lamp",
        "ha-device-id",
        IEEE,
        "source-lamp",
    ):
        assert secret not in encoded
    assert manager.diagnostics["failure_reason"] == "conflict"
    await manager.async_stop()
