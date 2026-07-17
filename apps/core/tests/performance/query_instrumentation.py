from __future__ import annotations

import re
import threading
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Mapping

SECRET_PATTERNS = ("0x", "password", "token", "payload_json", "body_json")


@dataclass
class QueryStats:
    execute_count: int = 0
    executemany_count: int = 0
    commit_count: int = 0
    rollback_count: int = 0
    statements: list[str] = field(default_factory=list)
    statement_counts: Counter[str] = field(default_factory=Counter)
    category_counts: Counter[str] = field(default_factory=Counter)

    def copy(self) -> "QueryStats":
        return QueryStats(
            self.execute_count,
            self.executemany_count,
            self.commit_count,
            self.rollback_count,
            list(self.statements),
            Counter(self.statement_counts),
            Counter(self.category_counts),
        )

    def delta(self, before: "QueryStats") -> "QueryStats":
        return QueryStats(
            self.execute_count - before.execute_count,
            self.executemany_count - before.executemany_count,
            self.commit_count - before.commit_count,
            self.rollback_count - before.rollback_count,
            self.statements[len(before.statements) :],
            self.statement_counts - before.statement_counts,
            self.category_counts - before.category_counts,
        )


def normalize_sql(sql: str) -> str:
    text = re.sub(r"\s+", " ", sql.strip())
    text = re.sub(r"\bVALUES\s*\([^)]*\)", "VALUES (?)", text, flags=re.I)
    text = re.sub(r"\bIN\s*\([^)]*\)", "IN (?)", text, flags=re.I)
    text = re.sub(r"'[^']*'", "?", text)
    text = re.sub(r"\b\d+\b", "?", text)
    return text


_TABLE_CATEGORIES = {
    "networks": ("read.networks", "write.networks"),
    "devices": ("read.devices", "write.devices"),
    "device_current_state": ("read.device_current_state", "write.device_current_state"),
    "device_snapshots": ("read.device_snapshots", "write.device_snapshots"),
    "availability_changes": ("read.availability_changes", "write.availability_changes"),
    "metric_samples": ("read.metric_samples", "write.metric_samples"),
    "health_snapshots": ("read.health_snapshots", "write.health_snapshots"),
    "incidents": ("read.incidents", "write.incidents"),
    "incident_devices": ("read.incident_devices", "write.incident_devices"),
    "incident_networks": ("read.incident_networks", "write.incident_networks"),
    "events": ("read.events", "write.events"),
    "topology_snapshots": ("read.topology_snapshots", "write.topology"),
    "topology_nodes": ("read.topology_nodes", "write.topology"),
    "topology_links": ("read.topology_links", "write.topology"),
    "ha_device_enrichment": ("read.ha_enrichment", "write.ha_enrichment"),
    "ha_enrichment_status": ("read.ha_enrichment", "write.ha_enrichment"),
    "sqlite_master": ("read.schema", "write.schema"),
    "schema_migrations": ("read.schema", "write.schema"),
    "collector_status": ("read.collector_status", "write.collector_status"),
    "bridge_snapshots": ("read.bridge_snapshots", "write.bridge_snapshots"),
    "unresolved_device_messages": ("read.unresolved", "write.unresolved"),
    "reports": ("read.reports", "write.reports"),
}


def classify_sql(sql: str) -> str:
    s = normalize_sql(sql).lower()
    if re.match(r"^(begin|commit|rollback)\b", s):
        return "transaction.control"
    write = bool(re.match(r"^(insert|update|delete|replace|create|drop|alter)\b", s))
    for table, (read_cat, write_cat) in _TABLE_CATEGORIES.items():
        if re.search(rf"\b{re.escape(table)}\b", s):
            return write_cat if write else read_cat
    return "other"


class CountingConnection:
    def __init__(self, wrapped: Any, stats: QueryStats | None = None) -> None:
        self._wrapped = wrapped
        self._stats = stats or QueryStats()
        self._lock = threading.RLock()

    @property
    def stats(self) -> QueryStats:
        return self._stats

    def reset(self) -> None:
        with self._lock:
            self._stats.execute_count = self._stats.executemany_count = 0
            self._stats.commit_count = self._stats.rollback_count = 0
            self._stats.statements.clear()
            self._stats.statement_counts.clear()
            self._stats.category_counts.clear()

    def snapshot(self) -> QueryStats:
        with self._lock:
            return self._stats.copy()

    def execute(self, sql: str, params: Any = ()) -> Any:
        # Record under the stats lock, then release before waiting on the DB lock.
        # Physical commit/rollback observers take only the stats lock and may run
        # while the DB lock is held — never hold stats -> DB.
        norm = normalize_sql(sql)
        category = classify_sql(norm)
        is_begin = bool(re.match(r"^begin\b", norm, flags=re.I))
        with self._lock:
            if not is_begin:
                self._stats.execute_count += 1
                self._stats.statements.append(norm)
                self._stats.statement_counts[norm] += 1
                self._stats.category_counts[category] += 1
            elif category == "transaction.control":
                # Keep BEGIN out of execute_count and out of `other`.
                pass
        return self._wrapped.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Any) -> Any:
        norm = normalize_sql(sql)
        category = classify_sql(norm)
        with self._lock:
            self._stats.executemany_count += 1
            self._stats.statements.append(norm)
            self._stats.statement_counts[norm] += 1
            self._stats.category_counts[category] += 1
        return self._wrapped.executemany(sql, seq_of_params)

    def commit(self) -> Any:
        if not hasattr(self._wrapped, "set_transaction_observer"):
            with self._lock:
                self._stats.commit_count += 1
                self._stats.category_counts["transaction.commit"] += 1
        return self._wrapped.commit()

    def rollback(self) -> Any:
        if not hasattr(self._wrapped, "set_transaction_observer"):
            with self._lock:
                self._stats.rollback_count += 1
                self._stats.category_counts["transaction.rollback"] += 1
        return self._wrapped.rollback()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


@dataclass(frozen=True)
class StatementCount:
    statement: str
    count: int


@dataclass(frozen=True)
class OperationMeasurement:
    name: str
    fixture_name: str
    state: str
    execute_count: int
    executemany_count: int
    commit_count: int
    rollback_count: int
    category_counts: Mapping[str, int]
    top_repeated_statements: tuple[StatementCount, ...]
    elapsed_ms: float | None = None


@contextmanager
def measure_queries(stats: QueryStats):
    before = stats.copy()
    start = time.perf_counter()
    box: dict[str, Any] = {}
    yield box
    delta = stats.delta(before)
    box["measurement"] = delta
    box["elapsed_ms"] = (time.perf_counter() - start) * 1000


def install_counter(repo: Any) -> CountingConnection:
    locked = repo.db.conn
    counter = CountingConnection(locked)

    def on_commit() -> None:
        with counter._lock:
            counter._stats.commit_count += 1
            counter._stats.category_counts["transaction.commit"] += 1

    def on_rollback() -> None:
        with counter._lock:
            counter._stats.rollback_count += 1
            counter._stats.category_counts["transaction.rollback"] += 1

    if hasattr(locked, "set_transaction_observer"):
        locked.set_transaction_observer(on_commit=on_commit, on_rollback=on_rollback)
    repo.db._locked = counter  # test-only seam at Database connection boundary
    return counter


@dataclass(frozen=True)
class PhaseMeasurement:
    name: str
    ingestion_execute_count: int
    ingestion_commit_count: int
    ingestion_rollback_count: int
    post_commit_execute_count: int
    post_commit_commit_count: int
    post_commit_rollback_count: int
    total_execute_count: int
    total_commit_count: int
    total_rollback_count: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "ingestion_execute_count": self.ingestion_execute_count,
            "ingestion_commit_count": self.ingestion_commit_count,
            "ingestion_rollback_count": self.ingestion_rollback_count,
            "post_commit_execute_count": self.post_commit_execute_count,
            "post_commit_commit_count": self.post_commit_commit_count,
            "post_commit_rollback_count": self.post_commit_rollback_count,
            "total_execute_count": self.total_execute_count,
            "total_commit_count": self.total_commit_count,
            "total_rollback_count": self.total_rollback_count,
        }


class PhaseAccumulator:
    """Accumulate ingestion vs post-commit counters across health callbacks."""

    def __init__(self, counter: CountingConnection) -> None:
        self._counter = counter
        self._mark = QueryStats()
        self.ingestion = QueryStats()
        self.post_commit = QueryStats()

    def on_callback_entry(self) -> QueryStats:
        """Capture ingestion delta. Call at health-callback entry (post physical commit)."""
        now = self._counter.snapshot()
        delta = now.delta(self._mark)
        self.ingestion = QueryStats(
            self.ingestion.execute_count + delta.execute_count,
            self.ingestion.executemany_count + delta.executemany_count,
            self.ingestion.commit_count + delta.commit_count,
            self.ingestion.rollback_count + delta.rollback_count,
            self.ingestion.statements + delta.statements,
            self.ingestion.statement_counts + delta.statement_counts,
            self.ingestion.category_counts + delta.category_counts,
        )
        self._mark = now
        return delta

    def on_callback_exit(self) -> QueryStats:
        now = self._counter.snapshot()
        delta = now.delta(self._mark)
        self.post_commit = QueryStats(
            self.post_commit.execute_count + delta.execute_count,
            self.post_commit.executemany_count + delta.executemany_count,
            self.post_commit.commit_count + delta.commit_count,
            self.post_commit.rollback_count + delta.rollback_count,
            self.post_commit.statements + delta.statements,
            self.post_commit.statement_counts + delta.statement_counts,
            self.post_commit.category_counts + delta.category_counts,
        )
        self._mark = now
        return delta

    def finish(self, name: str) -> PhaseMeasurement:
        total = self._counter.snapshot()
        trailing = total.delta(self._mark)
        if (
            trailing.execute_count
            or trailing.commit_count
            or trailing.rollback_count
            or trailing.executemany_count
        ):
            self.post_commit = QueryStats(
                self.post_commit.execute_count + trailing.execute_count,
                self.post_commit.executemany_count + trailing.executemany_count,
                self.post_commit.commit_count + trailing.commit_count,
                self.post_commit.rollback_count + trailing.rollback_count,
                self.post_commit.statements + trailing.statements,
                self.post_commit.statement_counts + trailing.statement_counts,
                self.post_commit.category_counts + trailing.category_counts,
            )
        return PhaseMeasurement(
            name=name,
            ingestion_execute_count=self.ingestion.execute_count,
            ingestion_commit_count=self.ingestion.commit_count,
            ingestion_rollback_count=self.ingestion.rollback_count,
            post_commit_execute_count=self.post_commit.execute_count,
            post_commit_commit_count=self.post_commit.commit_count,
            post_commit_rollback_count=self.post_commit.rollback_count,
            total_execute_count=total.execute_count,
            total_commit_count=total.commit_count,
            total_rollback_count=total.rollback_count,
        )


def measure_operation(
    name: str, fixture_name: str, state: str, stats: QueryStats, operation
) -> OperationMeasurement:
    before = stats.copy()
    start = time.perf_counter()
    operation()
    elapsed = (time.perf_counter() - start) * 1000
    delta = stats.delta(before)
    repeated = tuple(
        StatementCount(stmt, count) for stmt, count in delta.statement_counts.most_common(5)
    )
    return OperationMeasurement(
        name,
        fixture_name,
        state,
        delta.execute_count,
        delta.executemany_count,
        delta.commit_count,
        delta.rollback_count,
        dict(delta.category_counts),
        repeated,
        elapsed,
    )
