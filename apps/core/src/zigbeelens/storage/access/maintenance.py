"""Narrow storage-maintenance access layer (Track 6).

Preview and deletion share the same retention_instant eligibility expressions.
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
    JD_GE,
    JD_LE,
    JD_LT,
    JD_MALFORMED,
    MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS,
    MAINTENANCE_STATUS_KEY,
    StorageMaintenancePlan,
    StorageRetentionPreview,
    TELEMETRY_CATEGORIES,
    batches_required,
)
from zigbeelens.storage.repository import utc_now_iso

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository

# Keep equal to topology.service.PENDING_CAPTURE_TIMEOUT_SECONDS (15 minutes).
# Duplicated here to avoid importing the topology runtime into storage access.
_PENDING_CAPTURE_TIMEOUT_SECONDS = 15 * 60


class MaintenanceRepository:
    # Test-visible peak bind-parameter counts for topology exclude lists.
    max_exclude_bind_params_seen: int = 0

    def __init__(self, repo: Repository) -> None:
        self._repo = repo
        self.max_exclude_bind_params_seen = 0

    @property
    def db(self):
        return self._repo.db

    def preview_retention(self, plan: StorageMaintenancePlan) -> StorageRetentionPreview:
        by_category: dict[str, CategoryEligibility] = {}
        cutoffs = plan.cutoffs
        telemetry_iso = cutoffs.telemetry_iso()
        now_iso = plan.reference_now_iso()
        exclude = plan.exclude_topology_snapshot_ids

        for table, column, _pk in TELEMETRY_CATEGORIES:
            if not self._has_table(table):
                by_category[table] = CategoryEligibility()
                continue
            by_category[table] = self._count_age_category(
                table, column, telemetry_iso, now_iso
            )

        by_category["topology_snapshots"] = self._count_topology_age(
            telemetry_iso, now_iso, exclude_ids=exclude
        )
        by_category["incidents_resolved"] = self._count_resolved_incidents(
            cutoffs.resolved_incident_iso(), now_iso
        )
        by_category["reports"] = self._count_reports(cutoffs.report_iso(), now_iso)

        abandoned = self.count_abandoned_pending_topology(
            reference_now_iso=now_iso,
            exclude_ids=exclude,
        )
        count_cap = self.count_topology_count_cap_candidates(
            plan.policy.topology_max_snapshots_per_network,
            telemetry_cutoff_iso=telemetry_iso,
            reference_now_iso=now_iso,
            exclude_ids=exclude,
        )

        eligible_deletes = {
            name: item.eligible for name, item in by_category.items() if item.eligible
        }
        if count_cap:
            eligible_deletes["topology_count_cap"] = count_cap
        eligible_updates: dict[str, int] = {}
        if abandoned:
            eligible_updates["abandoned_pending_topology"] = abandoned

        malformed = {
            name: item.malformed_timestamps
            for name, item in by_category.items()
            if item.malformed_timestamps
        }
        future = {
            name: item.future_timestamps
            for name, item in by_category.items()
            if item.future_timestamps
        }
        batch_size = plan.batch_size
        batches = {
            name: batches_required(count, batch_size)
            for name, count in {**eligible_deletes, **eligible_updates}.items()
            if count
        }
        more = any(count >= batch_size for count in eligible_deletes.values()) or any(
            count >= batch_size for count in eligible_updates.values()
        )

        return StorageRetentionPreview(
            cutoffs=cutoffs,
            reference_now=plan.reference_now,
            eligible_deletes_by_category=eligible_deletes,
            eligible_updates_by_category=eligible_updates,
            malformed_timestamps_by_category=malformed,
            future_timestamps_by_category=future,
            batches_required_by_category=batches,
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
        cur = self.db.conn.execute(sql, (cutoff_iso, cutoff_iso, limit))
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
            (cutoff_iso, cutoff_iso, limit),
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
            (cutoff_iso, cutoff_iso, limit),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def purge_report_batch(self, cutoff_iso: str, *, limit: int) -> int:
        ids = self.select_report_ids(cutoff_iso, limit=limit)
        if not ids:
            return 0
        return self._delete_by_ids("reports", "id", ids)

    def select_terminal_topology_ids(
        self,
        cutoff_iso: str,
        *,
        limit: int,
        exclude_ids: frozenset[str] | None = None,
    ) -> list[str]:
        exclude_sql, exclude_params = self._exclude_clause(exclude_ids)
        cur = self.db.conn.execute(
            f"""
            SELECT snapshot_id FROM topology_snapshots
            WHERE status IN ('complete', 'error')
              AND {JD_LT.format(column="captured_at")}
              {exclude_sql}
            ORDER BY julianday(captured_at) ASC, snapshot_id ASC
            LIMIT ?
            """,
            (cutoff_iso, cutoff_iso, *exclude_params, limit),
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

    def purge_topology_age_batch(
        self,
        cutoff_iso: str,
        *,
        limit: int,
        exclude_ids: frozenset[str] | None = None,
    ) -> int:
        ids = self.select_terminal_topology_ids(
            cutoff_iso, limit=limit, exclude_ids=exclude_ids
        )
        return self.purge_topology_batch(ids)

    def select_abandoned_pending_topology_ids(
        self,
        *,
        pending_timeout_seconds: int = _PENDING_CAPTURE_TIMEOUT_SECONDS,
        reference_now_iso: str,
        limit: int,
        exclude_ids: frozenset[str] | None = None,
    ) -> list[str]:
        if not self._has_table("topology_snapshots"):
            return []
        exclude_sql, exclude_params = self._exclude_clause(exclude_ids)
        cur = self.db.conn.execute(
            f"""
            SELECT snapshot_id FROM topology_snapshots
            WHERE status = 'pending'
              AND julianday(captured_at) IS NOT NULL
              AND (retention_instant(?) - retention_instant(captured_at)) >= ?
              {exclude_sql}
            ORDER BY julianday(captured_at) ASC, snapshot_id ASC
            LIMIT ?
            """,
            (reference_now_iso, float(pending_timeout_seconds), *exclude_params, limit),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def terminalize_abandoned_topology_captures(
        self,
        *,
        pending_timeout_seconds: int = _PENDING_CAPTURE_TIMEOUT_SECONDS,
        reference_now_iso: str,
        limit: int,
        exclude_ids: frozenset[str] | None = None,
    ) -> list[str]:
        """Mark abandoned pending captures as error (bounded batch).

        Returns the snapshot IDs that were terminalized. Newly terminalized rows
        are not deleted in the same cycle.
        """
        ids = self.select_abandoned_pending_topology_ids(
            pending_timeout_seconds=pending_timeout_seconds,
            reference_now_iso=reference_now_iso,
            limit=limit,
            exclude_ids=exclude_ids,
        )
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        self.db.conn.execute(
            f"""
            UPDATE topology_snapshots
            SET status = 'error',
                error = ?
            WHERE snapshot_id IN ({placeholders})
              AND status = 'pending'
            """,
            (ABANDONED_TOPOLOGY_ERROR, *ids),
        )
        return list(ids)

    def count_abandoned_pending_topology(
        self,
        *,
        pending_timeout_seconds: int = _PENDING_CAPTURE_TIMEOUT_SECONDS,
        reference_now_iso: str,
        exclude_ids: frozenset[str] | None = None,
    ) -> int:
        if not self._has_table("topology_snapshots"):
            return 0
        exclude_sql, exclude_params = self._exclude_clause(exclude_ids)
        cur = self.db.conn.execute(
            f"""
            SELECT COUNT(*) FROM topology_snapshots
            WHERE status = 'pending'
              AND julianday(captured_at) IS NOT NULL
              AND (retention_instant(?) - retention_instant(captured_at)) >= ?
              {exclude_sql}
            """,
            (reference_now_iso, float(pending_timeout_seconds), *exclude_params),
        )
        return int(cur.fetchone()[0])

    def select_topology_count_cap_ids(
        self,
        max_snapshots: int,
        *,
        telemetry_cutoff_iso: str,
        reference_now_iso: str,
        limit: int,
        network_id: str | None = None,
        exclude_ids: frozenset[str] | None = None,
    ) -> list[str]:
        """Bounded excess terminal snapshots after age eligibility is excluded.

        Only rows with valid timestamps that are not age-eligible and not future
        compete for the count-cap slots. Malformed/future rows do not consume
        slots and are never deleted to compensate.
        """
        if max_snapshots < 1 or limit < 1:
            return []
        if not self._has_table("topology_snapshots"):
            return []
        exclude_sql, exclude_params = self._exclude_clause(exclude_ids, alias="t")
        network_sql = ""
        network_params: list[Any] = []
        if network_id is not None:
            network_sql = "AND t.network_id = ?"
            network_params = [network_id]
        cur = self.db.conn.execute(
            f"""
            SELECT snapshot_id FROM (
                SELECT
                    t.snapshot_id AS snapshot_id,
                    julianday(t.captured_at) AS captured_jd,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.network_id
                        ORDER BY julianday(t.captured_at) DESC, t.snapshot_id DESC
                    ) AS rn
                FROM topology_snapshots AS t
                WHERE t.status IN ('complete', 'error')
                  AND julianday(t.captured_at) IS NOT NULL
                  AND {JD_GE.format(column="t.captured_at")}
                  AND {JD_LE.format(column="t.captured_at")}
                  {network_sql}
                  {exclude_sql}
            )
            WHERE rn > ?
            ORDER BY captured_jd ASC, snapshot_id ASC
            LIMIT ?
            """,
            (
                telemetry_cutoff_iso,
                telemetry_cutoff_iso,
                reference_now_iso,
                reference_now_iso,
                *network_params,
                *exclude_params,
                max_snapshots,
                limit,
            ),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def count_topology_count_cap_candidates(
        self,
        max_snapshots: int,
        *,
        telemetry_cutoff_iso: str,
        reference_now_iso: str,
        exclude_ids: frozenset[str] | None = None,
    ) -> int:
        if not self._has_table("topology_snapshots") or max_snapshots < 1:
            return 0
        exclude_sql, exclude_params = self._exclude_clause(exclude_ids, alias="t")
        cur = self.db.conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT
                    t.snapshot_id AS snapshot_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.network_id
                        ORDER BY julianday(t.captured_at) DESC, t.snapshot_id DESC
                    ) AS rn
                FROM topology_snapshots AS t
                WHERE t.status IN ('complete', 'error')
                  AND julianday(t.captured_at) IS NOT NULL
                  AND {JD_GE.format(column="t.captured_at")}
                  AND {JD_LE.format(column="t.captured_at")}
                  {exclude_sql}
            )
            WHERE rn > ?
            """,
            (
                telemetry_cutoff_iso,
                telemetry_cutoff_iso,
                reference_now_iso,
                reference_now_iso,
                *exclude_params,
                max_snapshots,
            ),
        )
        return int(cur.fetchone()[0])

    def purge_topology_count_cap_batch(
        self,
        max_snapshots: int,
        *,
        telemetry_cutoff_iso: str,
        reference_now_iso: str,
        limit: int,
        network_id: str | None = None,
        exclude_ids: frozenset[str] | None = None,
    ) -> int:
        ids = self.select_topology_count_cap_ids(
            max_snapshots,
            telemetry_cutoff_iso=telemetry_cutoff_iso,
            reference_now_iso=reference_now_iso,
            limit=limit,
            network_id=network_id,
            exclude_ids=exclude_ids,
        )
        return self.purge_topology_batch(ids)

    def enforce_topology_count_retention(
        self,
        network_id: str,
        max_snapshots: int,
        *,
        telemetry_cutoff_iso: str | None = None,
        reference_now_iso: str | None = None,
        exclude_ids: frozenset[str] | None = None,
    ) -> int:
        """Canonical bounded count retention for one network (TopologyService).

        Repeats ≤500-ID batches until the network is within cap. Failures must
        be handled by the caller without marking a newly stored capture failed.
        """
        if max_snapshots < 1:
            return 0
        now_iso = reference_now_iso or utc_now_iso()
        # When called outside age retention, treat "no age cutoff" as epoch so
        # all valid non-future terminal rows compete for the count cap.
        cutoff_iso = telemetry_cutoff_iso or "1970-01-01T00:00:00+00:00"
        deleted = 0
        while True:
            with self._repo.transaction():
                batch = self.purge_topology_count_cap_batch(
                    max_snapshots,
                    telemetry_cutoff_iso=cutoff_iso,
                    reference_now_iso=now_iso,
                    limit=500,
                    network_id=network_id,
                    exclude_ids=exclude_ids,
                )
            deleted += batch
            if batch < 500:
                break
        return deleted

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
        cur = self.db.conn.execute(
            sql, ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00")
        )
        return [" | ".join(str(part) for part in row) for row in cur.fetchall()]

    def explain_topology_count_cap_select(self) -> list[str]:
        sql = f"""
            EXPLAIN QUERY PLAN
            SELECT snapshot_id FROM (
                SELECT
                    t.snapshot_id AS snapshot_id,
                    julianday(t.captured_at) AS captured_jd,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.network_id
                        ORDER BY julianday(t.captured_at) DESC, t.snapshot_id DESC
                    ) AS rn
                FROM topology_snapshots AS t
                WHERE t.status IN ('complete', 'error')
                  AND julianday(t.captured_at) IS NOT NULL
                  AND {JD_GE.format(column="t.captured_at")}
                  AND {JD_LE.format(column="t.captured_at")}
            )
            WHERE rn > ?
            ORDER BY captured_jd ASC, snapshot_id ASC
            LIMIT 500
        """
        cut = "2000-01-01T00:00:00+00:00"
        now = "2100-01-01T00:00:00+00:00"
        cur = self.db.conn.execute(sql, (cut, cut, now, now, 30))
        return [" | ".join(str(part) for part in row) for row in cur.fetchall()]

    def explain_abandoned_pending_select(self) -> list[str]:
        sql = """
            EXPLAIN QUERY PLAN
            SELECT snapshot_id FROM topology_snapshots
            WHERE status = 'pending'
              AND julianday(captured_at) IS NOT NULL
              AND (retention_instant(?) - retention_instant(captured_at)) >= ?
            ORDER BY julianday(captured_at) ASC, snapshot_id ASC
            LIMIT 500
        """
        cur = self.db.conn.execute(sql, ("2100-01-01T00:00:00+00:00", 900.0))
        return [" | ".join(str(part) for part in row) for row in cur.fetchall()]

    def explain_topology_age_select(self) -> list[str]:
        sql = f"""
            EXPLAIN QUERY PLAN
            SELECT snapshot_id FROM topology_snapshots
            WHERE status IN ('complete', 'error')
              AND {JD_LT.format(column="captured_at")}
            ORDER BY julianday(captured_at) ASC, snapshot_id ASC
            LIMIT 500
        """
        cut = "2000-01-01T00:00:00+00:00"
        cur = self.db.conn.execute(sql, (cut, cut))
        return [" | ".join(str(part) for part in row) for row in cur.fetchall()]

    def explain_incident_event_null_select(self) -> list[str]:
        cur = self.db.conn.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT id FROM events WHERE incident_id = ?
            """,
            ("x",),
        )
        return [" | ".join(str(part) for part in row) for row in cur.fetchall()]

    def explain_resolved_incident_select(self) -> list[str]:
        sql = f"""
            EXPLAIN QUERY PLAN
            SELECT id FROM incidents
            WHERE lifecycle_state = 'resolved'
              AND resolved_at IS NOT NULL
              AND {JD_LT.format(column="resolved_at")}
            ORDER BY julianday(resolved_at) ASC, id ASC
            LIMIT 500
        """
        cut = "2000-01-01T00:00:00+00:00"
        cur = self.db.conn.execute(sql, (cut, cut))
        return [" | ".join(str(part) for part in row) for row in cur.fetchall()]

    def _count_age_category(
        self, table: str, column: str, cutoff_iso: str, now_iso: str
    ) -> CategoryEligibility:
        eligible = self._scalar(
            f"SELECT COUNT(*) FROM {table} WHERE {JD_LT.format(column=column)}",
            (cutoff_iso, cutoff_iso),
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

    def _count_topology_age(
        self,
        cutoff_iso: str,
        now_iso: str,
        *,
        exclude_ids: frozenset[str] | None = None,
    ) -> CategoryEligibility:
        if not self._has_table("topology_snapshots"):
            return CategoryEligibility()
        exclude_sql, exclude_params = self._exclude_clause(exclude_ids)
        eligible = self._scalar(
            f"""
            SELECT COUNT(*) FROM topology_snapshots
            WHERE status IN ('complete', 'error')
              AND {JD_LT.format(column="captured_at")}
              {exclude_sql}
            """,
            (cutoff_iso, cutoff_iso, *exclude_params),
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
            (cutoff_iso, cutoff_iso),
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

    def _exclude_clause(
        self,
        exclude_ids: frozenset[str] | None,
        *,
        alias: str | None = None,
    ) -> tuple[str, list[str]]:
        if not exclude_ids:
            return "", []
        if len(exclude_ids) > MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS:
            raise ValueError(
                "topology exclude list exceeds MAINTENANCE_MAX_TOPOLOGY_EXCLUDE_IDS"
            )
        self.max_exclude_bind_params_seen = max(
            self.max_exclude_bind_params_seen, len(exclude_ids)
        )
        column = f"{alias}.snapshot_id" if alias else "snapshot_id"
        placeholders = ",".join("?" for _ in exclude_ids)
        return f"AND {column} NOT IN ({placeholders})", list(exclude_ids)

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
