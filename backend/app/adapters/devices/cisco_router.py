"""Cisco IOS / IOS-XE router collector (live RESTCONF + mock IOS CLI parser)."""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx

from app.adapters.devices.base import DeviceCollector, DeviceFetchResult, NormalizedRoute
from app.adapters.devices.mock_fixtures import CISCO_ROUTER_AFTER_CLI, CISCO_ROUTER_BEFORE_CLI
from app.adapters.devices.parsers import canonicalize_prefix, parse_cisco_ios_cli


class CiscoRouterCollector(DeviceCollector):
    """Collects routing tables from Cisco IOS / IOS-XE routers."""

    def __init__(
        self,
        *,
        device_id: int | None,
        hostname: str,
        ip_address: str,
        connection_mode: str = "mock",
        config_json: dict | None = None,
    ) -> None:
        self.device_id = device_id
        self.hostname = hostname
        self.ip_address = ip_address
        self.connection_mode = connection_mode
        self.config_json = config_json or {}

    async def collect_routes(
        self,
        phase: Literal["pre_change", "post_change", "adhoc"] = "adhoc",
    ) -> DeviceFetchResult:
        if self.connection_mode == "live":
            routes = await self._collect_live_restconf()
            notes = "Collected via Cisco IOS-XE RESTCONF (ietf-routing)"
        else:
            raw_cli = CISCO_ROUTER_BEFORE_CLI if phase == "pre_change" else CISCO_ROUTER_AFTER_CLI
            routes = await asyncio.to_thread(parse_cisco_ios_cli, raw_cli, self.hostname)
            notes = f"Collected via simulated IOS-XE transport + production IOS parser (phase={phase})"

        unique_prefixes = len({(r.vrf, r.prefix) for r in routes})
        return DeviceFetchResult(
            device_id=self.device_id,
            hostname=self.hostname,
            ip_address=self.ip_address,
            device_type="cisco_router",
            routes=routes,
            raw_entry_count=len(routes),
            unique_prefix_count=unique_prefixes,
            collector_notes=notes,
        )

    async def _collect_live_restconf(self) -> list[NormalizedRoute]:
        username = str(self.config_json.get("username") or "")
        password = str(self.config_json.get("password") or "")
        url = f"https://{self.ip_address}/restconf/data/ietf-routing:routing-state/routing-instance"
        headers = {"Accept": "application/yang-data+json"}
        async with httpx.AsyncClient(
            auth=(username, password),
            headers=headers,
            timeout=20.0,
            verify=bool(self.config_json.get("verify_ssl", False)),
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            instances = resp.json().get("ietf-routing:routing-instance", [])
            routes: list[NormalizedRoute] = []
            for inst in instances:
                vrf = str(inst.get("name") or "default")
                for rib in inst.get("ribs", {}).get("rib", []):
                    for route in rib.get("routes", {}).get("route", []):
                        raw_prefix = route.get("destination-prefix")
                        if not raw_prefix:
                            continue
                        ad = route.get("route-preference")
                        metric = route.get("metric")
                        nh_block = route.get("next-hop", {})
                        proto = str(route.get("source-protocol") or "unknown").split(":")[-1]
                        routes.append(
                            NormalizedRoute(
                                prefix=canonicalize_prefix(raw_prefix),
                                vrf=vrf,
                                next_hop=str(nh_block.get("next-hop-address") or ""),
                                interface=str(nh_block.get("outgoing-interface") or ""),
                                protocol=proto,
                                admin_distance=int(ad) if ad is not None else None,
                                metric=int(metric) if metric is not None else None,
                                raw_metric=f"{metric} (AD:{ad}, {proto.upper()})"
                                if metric is not None and ad is not None
                                else "",
                                appliance=self.hostname,
                            )
                        )
            return routes
