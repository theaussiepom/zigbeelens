"""Lifecycle owner for Home Assistant → ZigbeeLens enrichment snapshots."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .api import HomeAssistantEnrichmentResult
from .compatibility import EnrichmentContractState
from .exceptions import (
    ZigbeeLensAuthError,
    ZigbeeLensConnectionError,
    ZigbeeLensInvalidResponseError,
    ZigbeeLensRequestRejectedError,
    ZigbeeLensServerError,
)
from .ha_enrichment import (
    EnrichmentBuildResult,
    EnrichmentSnapshotState,
    CoreInventorySnapshot,
    HomeAssistantEnrichmentDevice,
    HomeAssistantRegistrySnapshot,
    RegistrySnapshotState,
    build_home_assistant_registry_snapshot,
    resolve_home_assistant_enrichment,
)

CancelCallback = Callable[[], None]
LaterScheduler = Callable[[float, Callable[[], None]], CancelCallback]
IntervalScheduler = Callable[[timedelta, Callable[[], None]], CancelCallback]
TaskFactory = Callable[
    [Coroutine[Any, Any, None]],
    asyncio.Future[None],
]
RegistryBuilder = Callable[[HomeAssistant], HomeAssistantRegistrySnapshot]


class EnrichmentSyncState(str, Enum):
    """Safe diagnostics state for the publisher lifecycle."""

    NEVER_ATTEMPTED = "never_attempted"
    SUCCESSFUL = "successful"
    SOURCE_UNAVAILABLE = "failed_source_unavailable"
    INVENTORY_UNAVAILABLE = "failed_inventory_unavailable"
    CONTRACT_UNSUPPORTED = "contract_unsupported"
    ROUTE_UNSUPPORTED = "failed_contract_unsupported"
    CONTRACT_MISSING = "contract_missing"
    CONTRACT_UNAVAILABLE = "failed_contract_unavailable"
    CONTRACT_MALFORMED = "contract_malformed"
    AUTHENTICATION_FAILED = "failed_authentication"
    CONNECTION_FAILED = "failed_connection"
    SERVER_FAILED = "failed_server"
    REQUEST_REJECTED = "failed_request_rejected"
    INVALID_RESPONSE = "failed_invalid_response"


@dataclass(frozen=True, slots=True)
class EnrichmentManagerDiagnostics:
    """Non-identifying manager facts safe to expose through diagnostics."""

    state: EnrichmentSyncState
    last_attempt_at: str | None
    last_success_at: str | None
    submitted: int | None
    matched: int | None
    unmatched: int | None
    ambiguous: int | None
    stored: int | None
    failure_reason: str | None

    def as_dict(self) -> dict[str, str | int | None]:
        """Return the exact identity-free shape consumed by diagnostics/repairs."""
        return {
            "sync_state": self.state.value,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "submitted": self.submitted,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "stored": self.stored,
            "failure_reason": self.failure_reason,
        }


class EnrichmentApiClient(Protocol):
    async def async_get_device_inventory(self) -> CoreInventorySnapshot: ...

    async def async_publish_home_assistant_enrichment(
        self,
        devices: tuple[HomeAssistantEnrichmentDevice, ...],
    ) -> HomeAssistantEnrichmentResult: ...


class EnrichmentConfigEntry(Protocol):
    def async_on_unload(
        self,
        func: Callable[[], Coroutine[Any, Any, None] | None],
    ) -> None: ...

    def async_start_reauth(
        self,
        hass: HomeAssistant,
        *,
        data: dict[str, Any] | None = None,
    ) -> None: ...


class HomeAssistantEnrichmentManager:
    """Own registry events, coalescing, retries, reconciliation, and cleanup."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EnrichmentConfigEntry,
        client: EnrichmentApiClient,
        *,
        capability_provider: Callable[[], EnrichmentContractState | bool | None],
        registry_builder: RegistryBuilder = build_home_assistant_registry_snapshot,
        later_scheduler: LaterScheduler | None = None,
        interval_scheduler: IntervalScheduler | None = None,
        task_factory: TaskFactory | None = None,
        now: Callable[[], str] | None = None,
        debounce_seconds: float = 2.0,
        retry_delays: tuple[float, ...] = (15.0, 60.0, 300.0),
        reconciliation_interval: timedelta = timedelta(minutes=15),
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._client = client
        self._capability_provider = capability_provider
        self._registry_builder = registry_builder
        self._later_scheduler = later_scheduler or self._default_later_scheduler
        self._interval_scheduler = (
            interval_scheduler or self._default_interval_scheduler
        )
        self._task_factory = task_factory or self._default_task_factory
        self._now = now or self._default_now
        self._debounce_seconds = debounce_seconds
        self._retry_delays = retry_delays
        self._reconciliation_interval = reconciliation_interval

        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Future[None]] = set()
        self._unsubscribers: list[CancelCallback] = []
        self._debounce_cancel: CancelCallback | None = None
        self._retry_cancel: CancelCallback | None = None
        self._periodic_cancel: CancelCallback | None = None
        self._retry_index = 0
        self._pending = False
        self._pending_force = False
        self._started = False
        self._stopped = False
        self._reauth_started = False
        self._last_fingerprint: str | None = None
        self._terminal_failure_fingerprint: str | None = None
        self._diagnostics = EnrichmentManagerDiagnostics(
            state=EnrichmentSyncState.NEVER_ATTEMPTED,
            last_attempt_at=None,
            last_success_at=None,
            submitted=None,
            matched=None,
            unmatched=None,
            ambiguous=None,
            stored=None,
            failure_reason=None,
        )

    @staticmethod
    def _default_now() -> str:
        return datetime.now(UTC).isoformat()

    def _default_later_scheduler(
        self,
        delay: float,
        action: Callable[[], None],
    ) -> CancelCallback:
        return async_call_later(self._hass, delay, lambda _now: action())

    def _default_interval_scheduler(
        self,
        interval: timedelta,
        action: Callable[[], None],
    ) -> CancelCallback:
        return async_track_time_interval(
            self._hass,
            lambda _now: action(),
            interval,
        )

    def _default_task_factory(
        self,
        coro: Coroutine[Any, Any, None],
    ) -> asyncio.Future[None]:
        return self._hass.async_create_task(coro)

    @property
    def diagnostics(self) -> dict[str, str | int | None]:
        """Return a fresh allowlisted mapping with no registry identities."""
        return self._diagnostics.as_dict()

    async def async_start(self) -> None:
        """Register lifecycle owners once and perform the initial sync."""
        if self._started:
            return
        self._started = True
        self._stopped = False
        self._unsubscribers.extend(
            (
                self._hass.bus.async_listen(
                    dr.EVENT_DEVICE_REGISTRY_UPDATED,
                    self._handle_registry_event,
                ),
                self._hass.bus.async_listen(
                    er.EVENT_ENTITY_REGISTRY_UPDATED,
                    self._handle_registry_event,
                ),
                self._hass.bus.async_listen(
                    ar.EVENT_AREA_REGISTRY_UPDATED,
                    self._handle_registry_event,
                ),
            )
        )
        self._periodic_cancel = self._interval_scheduler(
            self._reconciliation_interval,
            self._handle_periodic_reconciliation,
        )
        self._entry.async_on_unload(self.async_stop)
        await self.async_reconcile()

    async def async_stop(self) -> None:
        """Cancel every listener, timer, retry, and in-flight manager task."""
        if self._stopped:
            return
        self._stopped = True
        for cancel in (
            self._debounce_cancel,
            self._retry_cancel,
            self._periodic_cancel,
            *self._unsubscribers,
        ):
            if cancel is not None:
                cancel()
        self._debounce_cancel = None
        self._retry_cancel = None
        self._periodic_cancel = None
        self._unsubscribers.clear()

        current = asyncio.current_task()
        pending = [
            task for task in self._tasks if task is not current and not task.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._tasks.clear()

    @callback
    def _handle_registry_event(self, _event: Event) -> None:
        # Event payloads differ by HA release/action. Every registry update is
        # simply a signal to rebuild from the complete official registries.
        self.async_request_sync()

    @callback
    def _handle_periodic_reconciliation(self) -> None:
        # Force a bounded periodic re-publish so accepted metadata recovers
        # after a Core restart even when neither registry nor inventory changed.
        self._spawn(self.async_reconcile(force=True))

    @callback
    def async_request_sync(self) -> None:
        """Debounce and coalesce a registry event burst."""
        if self._stopped:
            return
        self._cancel_retry()
        if self._debounce_cancel is not None:
            self._debounce_cancel()
        self._debounce_cancel = self._later_scheduler(
            self._debounce_seconds,
            self._run_debounced,
        )

    @callback
    def _run_debounced(self) -> None:
        self._debounce_cancel = None
        self._spawn(self.async_reconcile())

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        if self._stopped:
            coro.close()
            return
        task = self._task_factory(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def async_wait_for_idle(self) -> None:
        """Test seam: wait for currently spawned work without sleeping."""
        pending = [task for task in self._tasks if not task.done()]
        if pending:
            await asyncio.gather(*pending)

    def _contract_state(self) -> EnrichmentContractState:
        try:
            raw = self._capability_provider()
        except Exception:
            return EnrichmentContractState.UNAVAILABLE
        if isinstance(raw, EnrichmentContractState):
            return raw
        if raw is True:
            return EnrichmentContractState.SUPPORTED
        if raw is False:
            return EnrichmentContractState.UNSUPPORTED
        return EnrichmentContractState.UNAVAILABLE

    def _set_diagnostics(
        self,
        state: EnrichmentSyncState,
        *,
        build: EnrichmentBuildResult | None = None,
        last_success_at: str | None = None,
        result: HomeAssistantEnrichmentResult | None = None,
        failure_reason: str | None = None,
        preserve_stored: bool = False,
    ) -> None:
        previous = self._diagnostics
        self._diagnostics = EnrichmentManagerDiagnostics(
            state=state,
            last_attempt_at=self._now(),
            last_success_at=(
                last_success_at
                if last_success_at is not None
                else previous.last_success_at
            ),
            submitted=(build.submitted_candidates if build is not None else 0)
            if build is not None
            else None,
            matched=len(build.devices) if build is not None else None,
            unmatched=build.unmatched if build is not None else None,
            ambiguous=build.ambiguous if build is not None else None,
            stored=(
                result.stored
                if result is not None
                else previous.stored
                if preserve_stored
                else None
            ),
            failure_reason=failure_reason,
        )

    async def async_reconcile(self, *, force: bool = False) -> None:
        """Build and publish at most one snapshot concurrently."""
        if self._stopped:
            return
        if self._lock.locked():
            self._pending = True
            self._pending_force = self._pending_force or force
            return

        async with self._lock:
            requested_force = force
            while not self._stopped:
                self._pending = False
                self._pending_force = False
                await self._async_reconcile_once(force=requested_force)
                if not self._pending:
                    break
                requested_force = self._pending_force

    async def _async_reconcile_once(self, *, force: bool) -> None:
        contract_state = self._contract_state()
        if contract_state is not EnrichmentContractState.SUPPORTED:
            # A capability transition is external Core state, so a later return
            # to supported must get one fresh attempt even for identical rows.
            self._terminal_failure_fingerprint = None
            state = {
                EnrichmentContractState.UNSUPPORTED: (
                    EnrichmentSyncState.CONTRACT_UNSUPPORTED
                ),
                EnrichmentContractState.MISSING: EnrichmentSyncState.CONTRACT_MISSING,
                EnrichmentContractState.UNAVAILABLE: (
                    EnrichmentSyncState.CONTRACT_UNAVAILABLE
                ),
                EnrichmentContractState.MALFORMED: (
                    EnrichmentSyncState.CONTRACT_MALFORMED
                ),
            }[contract_state]
            self._set_diagnostics(
                state,
                failure_reason=contract_state.value,
            )
            if contract_state is EnrichmentContractState.UNAVAILABLE:
                self._schedule_retry()
            else:
                self._cancel_retry()
            return

        registry = self._registry_builder(self._hass)
        if registry.state is RegistrySnapshotState.UNAVAILABLE:
            self._set_diagnostics(
                EnrichmentSyncState.SOURCE_UNAVAILABLE,
                failure_reason="registry_unavailable",
            )
            self._schedule_retry()
            return

        try:
            inventory = await self._client.async_get_device_inventory()
        except ZigbeeLensAuthError:
            self._set_diagnostics(
                EnrichmentSyncState.AUTHENTICATION_FAILED,
                failure_reason="authentication",
            )
            self._cancel_retry()
            self._start_reauth_once()
            return
        except ZigbeeLensConnectionError:
            self._set_diagnostics(
                EnrichmentSyncState.INVENTORY_UNAVAILABLE,
                failure_reason="inventory_connection",
            )
            self._schedule_retry()
            return
        except ZigbeeLensServerError as err:
            self._set_diagnostics(
                EnrichmentSyncState.SERVER_FAILED,
                failure_reason=err.category,
            )
            self._schedule_retry()
            return
        except ZigbeeLensRequestRejectedError as err:
            self._set_diagnostics(
                EnrichmentSyncState.REQUEST_REJECTED,
                failure_reason=err.category,
            )
            if err.status_code == 429:
                self._schedule_retry()
            else:
                self._cancel_retry()
            return
        except ZigbeeLensInvalidResponseError:
            self._set_diagnostics(
                EnrichmentSyncState.INVALID_RESPONSE,
                failure_reason="inventory_invalid_response",
            )
            self._schedule_retry()
            return

        build = resolve_home_assistant_enrichment(registry, inventory)
        if build.state is EnrichmentSnapshotState.UNAVAILABLE:
            self._set_diagnostics(
                EnrichmentSyncState.SOURCE_UNAVAILABLE,
                build=build,
                failure_reason="registry_unavailable",
            )
            self._schedule_retry()
            return
        fingerprint = build.fingerprint
        if fingerprint is None:
            self._set_diagnostics(
                EnrichmentSyncState.INVALID_RESPONSE,
                build=build,
                failure_reason="fingerprint_unavailable",
            )
            self._cancel_retry()
            return
        if not force and fingerprint == self._last_fingerprint:
            self._set_diagnostics(
                EnrichmentSyncState.SUCCESSFUL,
                build=build,
                preserve_stored=True,
            )
            return
        if not force and fingerprint == self._terminal_failure_fingerprint:
            previous = self._diagnostics
            self._set_diagnostics(
                previous.state,
                build=build,
                failure_reason=previous.failure_reason,
            )
            return

        try:
            result = await self._client.async_publish_home_assistant_enrichment(
                build.devices
            )
        except ZigbeeLensAuthError:
            self._set_diagnostics(
                EnrichmentSyncState.AUTHENTICATION_FAILED,
                build=build,
                failure_reason="authentication",
            )
            self._cancel_retry()
            self._start_reauth_once()
            return
        except ZigbeeLensConnectionError:
            self._set_diagnostics(
                EnrichmentSyncState.CONNECTION_FAILED,
                build=build,
                failure_reason="connection",
            )
            self._schedule_retry()
            return
        except ZigbeeLensServerError as err:
            self._set_diagnostics(
                EnrichmentSyncState.SERVER_FAILED,
                build=build,
                failure_reason=err.category,
            )
            self._schedule_retry()
            return
        except ZigbeeLensRequestRejectedError as err:
            state = (
                EnrichmentSyncState.ROUTE_UNSUPPORTED
                if err.status_code == 404
                else EnrichmentSyncState.REQUEST_REJECTED
            )
            self._set_diagnostics(
                state,
                build=build,
                failure_reason=err.category,
            )
            if err.status_code == 429:
                self._schedule_retry()
            else:
                self._terminal_failure_fingerprint = fingerprint
                self._cancel_retry()
            return
        except ZigbeeLensInvalidResponseError:
            self._set_diagnostics(
                EnrichmentSyncState.INVALID_RESPONSE,
                build=build,
                failure_reason="invalid_response",
            )
            self._terminal_failure_fingerprint = fingerprint
            self._cancel_retry()
            return

        self._last_fingerprint = fingerprint
        self._terminal_failure_fingerprint = None
        self._retry_index = 0
        self._cancel_retry()
        self._set_diagnostics(
            EnrichmentSyncState.SUCCESSFUL,
            build=build,
            last_success_at=result.last_push_at,
            result=result,
        )

    def _cancel_retry(self) -> None:
        if self._retry_cancel is None:
            return
        self._retry_cancel()
        self._retry_cancel = None

    def _schedule_retry(self) -> None:
        if self._stopped or not self._retry_delays or self._retry_cancel is not None:
            return
        index = min(self._retry_index, len(self._retry_delays) - 1)
        delay = self._retry_delays[index]
        self._retry_index = min(self._retry_index + 1, len(self._retry_delays) - 1)
        self._retry_cancel = self._later_scheduler(delay, self._run_retry)

    @callback
    def _run_retry(self) -> None:
        self._retry_cancel = None
        self._spawn(self.async_reconcile(force=True))

    def _start_reauth_once(self) -> None:
        if self._reauth_started:
            return
        self._reauth_started = True
        self._entry.async_start_reauth(self._hass)
