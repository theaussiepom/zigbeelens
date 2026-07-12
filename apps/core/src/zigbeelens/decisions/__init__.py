"""Shared decision-engine primitives.

Product judgement types live here so topology, devices, incidents and reports
can share one vocabulary without coupling to any single surface.
"""

from zigbeelens.decisions.coverage import (
    availability_history_building,
    availability_status_unknown,
    availability_tracking_off,
    battery_history_sparse,
    ha_areas_not_linked,
    lqi_history_sparse,
    route_hints_unavailable,
    snapshot_stale,
)
from zigbeelens.decisions.reasons import REASON_CODES, ReasonCode
from zigbeelens.decisions.topology_facts import (
    TOPOLOGY_FACT_CODES,
    TopologyFactCode,
    TopologyFacts,
    build_device_topology_facts,
    build_network_topology_facts,
    build_topology_facts_from_evidence_graph,
)
from zigbeelens.decisions.types import (
    CoverageDimension,
    CoverageLabelCode,
    CoverageState,
    DataCoverage,
    Decision,
    DecisionBundle,
    DecisionLimitation,
    DecisionPriority,
    DecisionReason,
    DecisionStatus,
    EvidenceFact,
    EvidenceReference,
    SuggestedCheck,
)

__all__ = [
    "REASON_CODES",
    "CoverageDimension",
    "CoverageLabelCode",
    "CoverageState",
    "DataCoverage",
    "Decision",
    "DecisionBundle",
    "DecisionLimitation",
    "DecisionPriority",
    "DecisionReason",
    "DecisionStatus",
    "EvidenceFact",
    "EvidenceReference",
    "ReasonCode",
    "SuggestedCheck",
    "TOPOLOGY_FACT_CODES",
    "TopologyFactCode",
    "TopologyFacts",
    "build_device_topology_facts",
    "build_network_topology_facts",
    "build_topology_facts_from_evidence_graph",
    "availability_history_building",
    "availability_status_unknown",
    "availability_tracking_off",
    "battery_history_sparse",
    "ha_areas_not_linked",
    "lqi_history_sparse",
    "route_hints_unavailable",
    "snapshot_stale",
]
