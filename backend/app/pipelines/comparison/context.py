"""Picklable context and data structures for the Comparison Pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class RoutePath:
    """Normalized single forwarding path associated with a (vrf, prefix) entry."""

    next_hop: str = ""
    interface: str = ""
    protocol: str = "unknown"
    admin_distance: int | None = None
    metric: int | None = None
    peer_priority: int | None = None
    raw_metric: str = ""

    def signature(self) -> tuple[str, str, str, int | None, int | None, int | None, str]:
        """Hashable identity used for exact multiset diffing of route paths."""
        return (
            self.next_hop,
            self.interface,
            self.protocol,
            self.admin_distance,
            self.metric,
            self.peer_priority,
            self.raw_metric,
        )

    def preference_key(self) -> tuple[int, int, int]:
        """Lexicographic route selection priority: (AD, Metric, PeerPriority) ascending."""
        return (
            self.admin_distance if self.admin_distance is not None else 999,
            self.metric if self.metric is not None else 999_999_999,
            self.peer_priority if self.peer_priority is not None else 999,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RouteDiffEntry:
    """Enriched difference record for a single (vrf, prefix) flowing through the pipeline."""

    vrf: str
    prefix: str
    prefix_len: int
    change_type: Literal["removed", "added", "changed"]
    before_paths: list[RoutePath] = field(default_factory=list)
    after_paths: list[RoutePath] = field(default_factory=list)
    removed_paths: list[RoutePath] = field(default_factory=list)
    added_paths: list[RoutePath] = field(default_factory=list)
    unchanged_path_count: int = 0

    # Stage 3: Importance classification
    is_important: bool = False
    matched_rules: list[str] = field(default_factory=list)
    importance_reasons: list[str] = field(default_factory=list)

    # Stage 4: Network semantics analysis
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] = "LOW"
    affected_ip_count: int = 0
    fallback_status: str | None = None  # default_or_blackhole | parent_same_egress | parent_different_egress
    fallback_parent_prefix: str | None = None
    fallback_parent_egress: str | None = None
    active_path_changed: bool | None = None
    backup_only_changed: bool | None = None
    best_before_summary: str | None = None
    best_after_summary: str | None = None
    next_hop_changes: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    # Stage 5: Final human-readable explanation
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "vrf": self.vrf,
            "prefix": self.prefix,
            "prefix_len": self.prefix_len,
            "change_type": self.change_type,
            "before_paths": [p.to_dict() for p in self.before_paths],
            "after_paths": [p.to_dict() for p in self.after_paths],
            "removed_paths": [p.to_dict() for p in self.removed_paths],
            "added_paths": [p.to_dict() for p in self.added_paths],
            "unchanged_path_count": self.unchanged_path_count,
            "is_important": self.is_important,
            "matched_rules": list(self.matched_rules),
            "importance_reasons": list(self.importance_reasons),
            "severity": self.severity,
            "affected_ip_count": self.affected_ip_count,
            "fallback_status": self.fallback_status,
            "fallback_parent_prefix": self.fallback_parent_prefix,
            "fallback_parent_egress": self.fallback_parent_egress,
            "active_path_changed": self.active_path_changed,
            "backup_only_changed": self.backup_only_changed,
            "best_before_summary": self.best_before_summary,
            "best_after_summary": self.best_after_summary,
            "next_hop_changes": list(self.next_hop_changes),
            "findings": list(self.findings),
            "explanation": self.explanation,
        }


@dataclass
class ComparisonInput:
    """Pure, picklable input bundle passed into the Comparison Pipeline."""

    device_label: str
    before_routes: list[dict[str, Any]]
    after_routes: list[dict[str, Any]]
    important_prefixes: list[str] = field(default_factory=list)
    large_prefix_threshold: int = 20


@dataclass
class ComparisonContext:
    """Mutable working state passed sequentially across all comparison pipeline stages."""

    input_data: ComparisonInput

    # Populated by Stage 1 (NormalizeStage)
    before_map: dict[tuple[str, str], list[RoutePath]] = field(default_factory=dict)
    after_map: dict[tuple[str, str], list[RoutePath]] = field(default_factory=dict)
    before_raw_count: int = 0
    after_raw_count: int = 0

    # Populated by Stage 2 (DiffStage)
    diff_entries: list[RouteDiffEntry] = field(default_factory=list)
    unchanged_prefix_count: int = 0

    # Populated by Stage 4 (NetworkAnalysisStage)
    overall_risk_level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "PASS"] = "PASS"
    total_affected_ips_excluding_default: int = 0

    # Populated by Stage 5 (ReportAssemblyStage)
    report_payload: dict[str, Any] = field(default_factory=dict)
