"""Report read/write access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zigbeelens.storage.repository import ReportRow

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class ReportRepository:
    """Narrow access layer for reports."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def save_report(
        self,
        *,
        report_id: str | None,
        format: str,
        summary: str,
        body: dict[str, Any],
        markdown: str | None = None,
        redaction: dict[str, Any] | None = None,
        scope: str = "full",
        redaction_profile: str = "standard",
        metadata: dict[str, Any] | None = None,
    ) -> ReportRow:
        return self._repo.save_report(
            report_id=report_id,
            format=format,
            summary=summary,
            body=body,
            markdown=markdown,
            redaction=redaction,
            scope=scope,
            redaction_profile=redaction_profile,
            metadata=metadata,
        )

    def get_report(self, report_id: str) -> ReportRow | None:
        return self._repo.get_report(report_id)

    def list_reports(self, limit: int = 50) -> list[ReportRow]:
        return self._repo.list_reports(limit=limit)

    def delete_report(self, report_id: str) -> bool:
        return self._repo.delete_report(report_id)
