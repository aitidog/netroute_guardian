"""Vendor-agnostic normalized route representation and collector contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class NormalizedRoute:
    """Canonical representation of a single route path across all supported vendors."""

    prefix: str
    vrf: str = "default"
    next_hop: str = ""
    interface: str = ""
    protocol: str = "unknown"
    admin_distance: int | None = None
    metric: int | None = None
    peer_priority: int | None = None
    raw_metric: str = ""
    appliance: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedRoute:
        return cls(
            prefix=data["prefix"],
            vrf=data.get("vrf", "default"),
            next_hop=data.get("next_hop", ""),
            interface=data.get("interface", ""),
            protocol=data.get("protocol", "unknown"),
            admin_distance=data.get("admin_distance"),
            metric=data.get("metric"),
            peer_priority=data.get("peer_priority"),
            raw_metric=data.get("raw_metric", ""),
            appliance=data.get("appliance", ""),
            extra=dict(data.get("extra") or {}),
        )


@dataclass
class DeviceFetchResult:
    """Outcome returned by a DeviceCollector for a single device."""

    device_id: int | None
    hostname: str
    ip_address: str
    device_type: str
    routes: list[NormalizedRoute]
    raw_entry_count: int
    unique_prefix_count: int
    collector_notes: str = ""


class DeviceCollector(ABC):
    """Abstract base class for collecting normalized routing tables from a network device."""

    @abstractmethod
    async def collect_routes(
        self,
        phase: Literal["pre_change", "post_change", "adhoc"] = "adhoc",
    ) -> DeviceFetchResult:
        """Fetch and parse the routing table for the specified workflow phase."""
