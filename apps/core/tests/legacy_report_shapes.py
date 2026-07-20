"""Historical report body helpers for immutable v1/v2 reader tests only.

These shapes must not participate in current preview/create/store/OpenAPI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from zigbeelens.schemas import Severity


class ReportSummaryBlock(BaseModel):
    overall_state: Severity
    current_finding: str
    networks_monitored: int
    total_devices: int
    active_incidents: int
    watching_incidents: int
    unavailable_devices: int
    router_risks: int
    stale_devices: int
    weak_links: int
    low_battery_devices: int


class LensHealthSummary(BaseModel):
    vocabulary: str = "lens_family"
    overall_state: str | None = None
    bucket_counts: dict[str, int] = Field(default_factory=dict)
    bucket_labels: dict[str, str] = Field(default_factory=dict)
