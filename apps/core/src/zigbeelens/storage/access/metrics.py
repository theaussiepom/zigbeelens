"""Metric sample read/write access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class MetricRepository:
    """Narrow access layer for metric_samples."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def insert_metric_sample(
        self, network_id: str, ieee_address: str, metric_name: str, metric_value: float
    ) -> None:
        self._repo.insert_metric_sample(network_id, ieee_address, metric_name, metric_value)

    def list_metric_samples(
        self, network_id: str, ieee_address: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return self._repo.list_metric_samples(network_id, ieee_address, limit)
