"""Narrow storage-maintenance access layer (Track 6).

Preview and deletion share the same julianday eligibility expressions.
Destructive methods must be called inside Repository.transaction().
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from zigbeelens.storage.retention_policy import (
    ABANDONED_TOPOLOGY_ERROR,
    CategoryEligibility,
    JD_FUTURE,
    JD_LT,
    JD_MALFORMED,
    MAINTENANCE_STATUS_KEY,
    StorageMaintenancePlan,
    StorageRetentionPreview,
    TELEMETRY_CATEGORIES,
)
from zigbeelens.storage.repository import utc_now_iso

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Keep equal to topology.service.PENDING_CAPTURE_TIMEOUT_SECONDS (15 minutes).
# Duplicated here to avoid importing the topology runtime into storage access.
_PENDING_CAPTURE_TIMEOUT_SECONDS = 15 * 60


class MaintenanceRepository:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    @property
    def db(self):
        return self._repo.db

    def preview_retention(self, plan: StorageMaintenancePlan) -> StorageRetentionPreview:
        by_category: dict[str, CategoryEligibility] = {}
        cutoffs = plan.cutoffs
        telemetry_iso = cutoffs.telemetry_iso()
        now_iso = utc_now_iso()

        for table, column, _pk in TELEMETRY_CATEGORIES:
            if not self._has_table(table):
                by_category[table] = CategoryEligibility()
                continue
            by_category[table] = self._count_age_category(
                table, column, telemetry_iso, now_iso
            )

        by_category["topology_snapshots"] = self._count_topology_age(telemetry_iso, now_iso)
        by_category["incidents_resolved"] = self._count_resolved_incidents(
            cutoffs.resolved_incident_iso(), now_iso
        )
        by_category["reports"] = self._count_reports(cutoffs.report_iso(), now_iso)

        abandoned = self.count_abandoned_pending_topology()
        count_cap = self.count_topology_count_cap_candidates(
            plan.policy.topology_max_snapshots_per_network
        )
        more = any(
            item.eligible >= plan.batch_size for item in by_category.values()
        ) or count_cap >= plan.batch_size

        return StorageRetentionPreview(
            cutoffs=cutoffs,
            by_category=by_category,
            topology_count_cap_candidates=count_cap,
            abandoned_pending_topology=abandoned,
            more_work_pending=more,
        )

    def select_telemetry_ids(
        self,
        table: str,
        column: str,
        pk: str,
        cutoff_iso: str,
        *,
        limit: int,
    ) -> list[Any]:
        sql = f"""
            SELECT {pk} FROM {table}
            WHERE {JD_LT.format(column=column)}
            ORDER BY julianday({column}) ASC, {pk} ASC
            LIMIT ?
        """
        cur = self.db.conn.execute(sql, (cutoff_iso, limit))
        return [row[0] for row in cur.fetchall()]

    def purge_telemetry_batch(
        self,
        table: str,
        column: str,
        pk: str,
        cutoff_iso: str,
        *,
        limit: int,
    ) -> int:
        ids = self.select_telemetry_ids(table, column, pk, cutoff_iso, limit=limit)
        if not ids:
            return 0
        return self._delete_by_ids(table, pk, ids)

    def select_resolved_incident_ids(self, cutoff_iso: str, *, limit: int) -> list[str]:
        cur = self.db.conn.execute(
            f"""
            SELECT id FROM incidents
            WHERE lifecycle_state = 'resolved'
              AND resolved_at IS NOT NULL
              AND {JD_LT.format(column="resolved_at")}
            ORDER BY julianday(resolved_at) ASC, id ASC
            LIMIT ?
            """,
            (cutoff_iso, limit),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def purge_resolved_incident_batch(self, cutoff_iso: str, *, limit: int) -> int:
        ids = self.select_resolved_incident_ids(cutoff_iso, limit=limit)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        self.db.conn.execute(
            f"""
            UPDATE events
            SET incident_id = NULL
            WHERE incident_id IN ({placeholders})
            """,
            ids,
        )
        cur = self.db.conn.execute(
            f"DELETE FROM incidents WHERE id IN ({placeholders})",
            ids,
        )
        return int(cur.rowcount)

    def select_report_ids(self, cutoff_iso: str, *, limit: int) -> list[str]:
        cur = self.db.conn.execute(
            f"""
            SELECT id FROM reports
            WHERE {JD_LT.format(column="generated_at")}
            ORDER BY julianday(generated_at) ASC, id ASC
            LIMIT ?
            """,
            (cutoff_iso, limit),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def purge_report_batch(self, cutoff_iso: str, *, limit: int) -> int:
        ids = self.select_report_ids(cutoff_iso, limit=limit)
        if not ids:
            return 0
        return self._delete_by_ids("reports", "id", ids)

    def select_terminal_topology_ids(self, cutoff_iso: str, *, limit: int) -> list[str]:
        cur = self.db.conn.execute(
            f"""
            SELECT snapshot_id FROM topology_snapshots
            WHERE status IN ('complete', 'error')
              AND {JD_LT.format(column="captured_at")}
            ORDER BY julianday(captured_at) ASC, snapshot_id ASC
            LIMIT ?
            """,
            (cutoff_iso, limit),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def purge_topology_batch(self, snapshot_ids: Sequence[str]) -> int:
        if not snapshot_ids:
            return 0
        placeholders = ",".join("?" for _ in snapshot_ids)
        params = list(snapshot_ids)
        self.db.conn.execute(
            f"DELETE FROM topology_links WHERE snapshot_id IN ({placeholders})",
            params,
        )
        self.db.conn.execute(
            f"DELETE FROM topology_nodes WHERE snapshot_id IN ({placeholders})",
            params,
        )
        cur = self.db.conn.execute(
            f"DELETE FROM topology_snapshots WHERE snapshot_id IN ({placeholders})",
            params,
        )
        return int(cur.rowcount)

    def purge_topology_age_batch(self, cutoff_iso: str, *, limit: int) -> int:
        ids = self.select_terminal_topology_ids(cutoff_iso, limit=limit)
        return self.purge_topology_batch(ids)

    def terminalize_abandoned_topology_captures(
        self,
        *,
        pending_timeout_seconds: int = _PENDING_CAPTURE_TIMEOUT_SECONDS,
        reference_now_iso: str | None = None,
    ) -> int:
        """Mark persisted pending captures older than the pending timeout as error.

        Does not publish Zigbee2MQTT requests or claim a capture failure from Z2M.
        """
        if not self._has_table("topology_snapshots"):
            return 0
        now_iso = reference_now_iso or utc_now_iso()
        # Age via julianday difference in days * 86400.
        cur = self.db.conn.execute(
            """
            UPDATE topology_snapshots
            SET status = 'error',
                error = ?
            WHERE status = 'pending'
              AND julianday(captured_at) IS NOT NULL
              AND (julianday(?) - julianday(captured_at)) * 86400.0 >= ?
            """,
            (ABANDONED_TOPOLOGY_ERROR, now_iso, float(pending_timeout_seconds)),
        )
        return int(cur.rowcount)

    def count_abandoned_pending_topology(
        self,
        *,
        pending_timeout_seconds: int = _PENDING_CAPTURE_TIMEOUT_SECONDS,
        reference_now_iso: str | None = None,
    ) -> int:
        if not self._has_table("topology_snapshots"):
            return 0
        now_iso = reference_now_iso or utc_now_iso()
        cur = self.db.conn.execute(
            """
            SELECT COUNT(*) FROM topology_snapshots
            WHERE status = 'pending'
              AND julianday(captured_at) IS NOT NULL
              AND (julianday(?) - julianday(captured_at)) * 86400.0 >= ?
            """,
            (now_iso, float(pending_timeout_seconds)),
        )
        return int(cur.fetchone()[0])

    def select_topology_count_cap_ids(
        self,
        network_id: str,
        max_snapshots: int,
        *,
        limit: int,
    ) -> list[str]:
        """Terminal snapshots beyond the newest *max_snapshots* for one network."""
        if max_snapshots < 1:
            return []
        cur = self.db.conn.execute(
            """
            SELECT snapshot_id FROM topology_snapshots
            WHERE network_id = ?
              AND status IN ('complete', 'error')
            ORDER BY julianday(captured_at) DESC, snapshot_id DESC
            """,
            (network_id,),
        )
        rows = [str(row[0]) for row in cur.fetchall()]
        excess = rows[max_snapshots:]
        # Delete oldest first among excess: reverse order of newest-first list.
        excess_oldest_first = list(reversed(excess))
        return excess_oldest_first[:limit]

    def count_topology_count_cap_candidates(self, max_snapshots: int) -> int:
        if not self._has_table("topology_snapshots") or max_snapshots < 1:
            return 0
        cur = self.db.conn.execute(
            """
            SELECT network_id, COUNT(*) AS n
            FROM topology_snapshots
            WHERE status IN ('complete', 'error')
            GROUP BY network_id
            HAVING n > ?
            """,
            (max_snapshots,),
        )
        total = 0
        for row in cur.fetchall():
            total += int(row["n"]) - max_snapshots
        return total

    def purge_topology_count_cap_batch(
        self,
        max_snapshots: int,
        *,
        limit: int,
    ) -> int:
        if not self._has_table("topology_snapshots") or max_snapshots < 1 or limit < 1:
            return 0
        cur = self.db.conn.execute(
            """
            SELECT DISTINCT network_id FROM topology_snapshots
            WHERE status IN ('complete', 'error')
            ORDER BY network_id ASC
            """
        )
        remaining = limit
        deleted = 0
        for row in cur.fetchall():
            if remaining <= 0:
                break
            ids = self.select_topology_count_cap_ids(
                str(row["network_id"]), max_snapshots, limit=remaining
            )
            if not ids:
                continue
            deleted += self.purge_topology_batch(ids)
            remaining -= len(ids)
        return deleted

    def enforce_topology_count_retention(self, network_id: str, max_snapshots: int) -> int:
        """Canonical count retention for one network (used by TopologyService)."""
        if max_snapshots < 1:
            return 0
        ids = self.select_topology_count_cap_ids(network_id, max_snapshots, limit=10_000)
        if not ids:
            return 0
        with self._repo.transaction():
            return self.purge_topology_batch(ids)

    def get_maintenance_setting(self) -> dict[str, Any] | None:
        cur = self.db.conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (MAINTENANCE_STATUS_KEY,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def set_maintenance_setting(self, payload: Mapping[str, Any]) -> None:
        now = utc_now_iso()
        self.db.conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (MAINTENANCE_STATUS_KEY, json.dumps(dict(payload), separators=(",", ":")), now),
        )

    def storage_footprint(self) -> dict[str, int | None]:
        db_path = Path(self.db.path)

        def _size(p: Path) -> int | None:
            try:
                if not p.exists():
                    return 0
                return int(p.stat().st_size)
            except OSError:
                return None

        main = _size(db_path)
        wal = _size(Path(str(db_path) + "-wal"))
        shm = _size(Path(str(db_path) + "-shm"))
        page_size = self._pragma_int("page_size")
        page_count = self._pragma_int("page_count")
        freelist = self._pragma_int("freelist_count")
        reusable = None
        if page_size is not None and freelist is not None:
            reusable = page_size * freelist
        total = None
        if main is not None and wal is not None and shm is not None:
            total = main + wal + shm
        schema_version = int(getattr(self.db, "migration_version", 0) or 0)
        return {
            "database_bytes": main,
            "wal_bytes": wal,
            "shm_bytes": shm,
            "total_sqlite_bytes": total,
            "page_size": page_size,
            "page_count": page_count,
            "freelist_page_count": freelist,
            "reusable_bytes": reusable,
            "schema_version": schema_version,
        }

    def explain_retention_select(self, table: str, column: str, pk: str) -> list[str]:
        """Return EXPLAIN QUERY PLAN lines for the principal age selector."""
        sql = f"""
            EXPLAIN QUERY PLAN
            SELECT {pk} FROM {table}
            WHERE {JD_LT.format(column=column)}
            ORDER BY julianday({column}) ASC, {pk} ASC
            LIMIT 500
        """
        cur = self.db.conn.execute(sql, ("2000-01-01T00:00:00+00:00",))
        return [" | ".join(str(part) for part in row) for row in cur.fetchall()]

    def _count_age_category(
        self, table: str, column: str, cutoff_iso: str, now_iso: str
    ) -> CategoryEligibility:
        eligible = self._scalar(
            f"SELECT COUNT(*) FROM {table} WHERE {JD_LT.format(column=column)}",
            (cutoff_iso,),
        )
        malformed = self._scalar(
            f"SELECT COUNT(*) FROM {table} WHERE {JD_MALFORMED.format(column=column)}"
        )
        future = self._scalar(
            f"SELECT COUNT(*) FROM {table} WHERE {JD_FUTURE.format(column=column)}",
            (now_iso,),
        )
        return CategoryEligibility(
            eligible=eligible, malformed_timestamps=malformed, future_timestamps=future
        )

    def _count_topology_age(self, cutoff_iso: str, now_iso: str) -> CategoryEligibility:
        if not self._has_table("topology_snapshots"):
            return CategoryEligibility()
        eligible = self._scalar(
            f"""
            SELECT COUNT(*) FROM topology_snapshots
            WHERE status IN ('complete', 'error')
              AND {JD_LT.format(column="captured_at")}
            """,
            (cutoff_iso,),
        )
        malformed = self._scalar(
            f"""
            SELECT COUNT(*) FROM topology_snapshots
            WHERE {JD_MALFORMED.format(column="captured_at")}
            """
        )
        future = self._scalar(
            f"""
            SELECT COUNT(*) FROM topology_snapshots
            WHERE {JD_FUTURE.format(column="captured_at")}
            """,
            (now_iso,),
        )
        return CategoryEligibility(
            eligible=eligible, malformed_timestamps=malformed, future_timestamps=future
        )

    def _count_resolved_incidents(
        self, cutoff_iso: str | None, now_iso: str
    ) -> CategoryEligibility:
        if cutoff_iso is None:
            return CategoryEligibility(
                eligible=0,
                malformed_timestamps=self._scalar(
                    f"""
                    SELECT COUNT(*) FROM incidents
                    WHERE lifecycle_state = 'resolved'
                      AND {JD_MALFORMED.format(column="resolved_at")}
                    """
                ),
                future_timestamps=self._scalar(
                    f"""
                    SELECT COUNT(*) FROM incidents
                    WHERE lifecycle_state = 'resolved'
                      AND resolved_at IS NOT NULL
                      AND {JD_FUTURE.format(column="resolved_at")}
                    """,
                    (now_iso,),
                ),
            )
        eligible = self._scalar(
            f"""
            SELECT COUNT(*) FROM incidents
            WHERE lifecycle_state = 'resolved'
              AND resolved_at IS NOT NULL
              AND {JD_LT.format(column="resolved_at")}
            """,
            (cutoff_iso,),
        )
        malformed = self._scalar(
            f"""
            SELECT COUNT(*) FROM incidents
            WHERE lifecycle_state = 'resolved'
              AND {JD_MALFORMED.format(column="resolved_at")}
            """
        )
        future = self._scalar(
            f"""
            SELECT COUNT(*) FROM incidents
            WHERE lifecycle_state = 'resolved'
              AND resolved_at IS NOT NULL
              AND {JD_FUTURE.format(column="resolved_at")}
            """,
            (now_iso,),
        )
        return CategoryEligibility(
            eligible=eligible, malformed_timestamps=malformed, future_timestamps=future
        )

    def _count_reports(self, cutoff_iso: str | None, now_iso: str) -> CategoryEligibility:
        if cutoff_iso is None:
            return CategoryEligibility(
                eligible=0,
                malformed_timestamps=self._scalar(
                    f"SELECT COUNT(*) FROM reports WHERE {JD_MALFORMED.format(column='generated_at')}"
                ),
                future_timestamps=self._scalar(
                    f"SELECT COUNT(*) FROM reports WHERE {JD_FUTURE.format(column='generated_at')}",
                    (now_iso,),
                ),
            )
        return self._count_age_category("reports", "generated_at", cutoff_iso, now_iso)

    def _delete_by_ids(self, table: str, pk: str, ids: Sequence[Any]) -> int:
        placeholders = ",".join("?" for _ in ids)
        cur = self.db.conn.execute(
            f"DELETE FROM {table} WHERE {pk} IN ({placeholders})",
            list(ids),
        )
        return int(cur.rowcount)

    def _has_table(self, name: str) -> bool:
        return self._repo._has_table(name)

    def _scalar(self, sql: str, params: Iterable[Any] = ()) -> int:
        cur = self.db.conn.execute(sql, tuple(params))
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _pragma_int(self, name: str) -> int | None:
        try:
            cur = self.db.conn.execute(f"PRAGMA {name}")
            row = cur.fetchone()
            if row is None or row[0] is None:
                return None
            return int(row[0])
        except sqlite3.Error:
            return None
