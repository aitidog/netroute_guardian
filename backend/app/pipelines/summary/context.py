"""Picklable context and output models for the Route Summary Pipeline."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SummaryInput:
    """Pure picklable input passed into the Route Summary Pipeline."""

    source_label: str
    routes: list[dict[str, Any]]
    include_supernet_suggestions: bool = False
    device_type: str | None = None
    device_ip: str | None = None


@dataclass
class CollapsedRouteNode:
    """Top-level retained prefix together with all more-specific routes it covers."""

    vrf: str
    prefix: str
    prefix_len: int
    covered_routes: list[str] = field(default_factory=list)

    @property
    def is_summary(self) -> bool:
        return len(self.covered_routes) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "vrf": self.vrf,
            "prefix": self.prefix,
            "prefix_len": self.prefix_len,
            "is_summary": self.is_summary,
            "covered_count": len(self.covered_routes),
            "covered_routes": list(self.covered_routes),
        }


@dataclass
class SummaryContext:
    """Mutable state flowing sequentially across all Route Summary Pipeline stages."""

    input_data: SummaryInput

    # Populated by Stage 1 (FilterNormalizeStage)
    total_raw_entries: int = 0
    ignored_default_routes: int = 0
    unique_networks_by_vrf: dict[str, list[ipaddress.IPv4Network | ipaddress.IPv6Network]] = field(
        default_factory=dict
    )

    # Populated by Stage 2 (PrefixCollapseStage)
    collapsed_by_vrf: dict[str, list[CollapsedRouteNode]] = field(default_factory=dict)

    # Populated by Stage 3 (SupernetSuggestionStage)
    supernet_suggestions: list[dict[str, Any]] | None = None

    # Populated by Stage 4 (SummaryFormatStage)
    result_payload: dict[str, Any] = field(default_factory=dict)
