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
        norm = normalize_sql(sql)
        with self._lock:
            self._stats.execute_count += 1
            self._stats.statements.append(norm)
            self._stats.statement_counts[norm] += 1
            self._stats.category_counts[classify_sql(norm)] += 1
            return self._wrapped.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Any) -> Any:
        norm = normalize_sql(sql)
        with self._lock:
            self._stats.executemany_count += 1
            self._stats.statements.append(norm)
            self._stats.statement_counts[norm] += 1
            self._stats.category_counts[classify_sql(norm)] += 1
            return self._wrapped.executemany(sql, seq_of_params)

    def commit(self) -> Any:
        with self._lock:
            self._stats.commit_count += 1
            self._stats.category_counts["transaction.commit"] += 1
        return self._wrapped.commit()

    def rollback(self) -> Any:
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
    counter = CountingConnection(repo.db.conn)
    repo.db._locked = counter  # test-only seam at Database connection boundary
    return counter


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
