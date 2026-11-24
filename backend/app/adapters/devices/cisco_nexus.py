"""Cisco Nexus (NX-OS) switch collector (live NX-API JSON-RPC + mock NX-OS CLI parser)."""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx

from app.adapters.devices.base import DeviceCollector, DeviceFetchResult
from app.adapters.devices.mock_fixtures import CISCO_NEXUS_AFTER_CLI, CISCO_NEXUS_BEFORE_CLI
from app.adapters.devices.parsers import parse_cisco_nxapi_json, parse_cisco_nxos_cli


class CiscoNexusCollector(DeviceCollector):
    """Collects routing tables from Cisco Nexus switches."""

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
            routes = await self._collect_live_nxapi()
            notes = "Collected via Cisco NX-API JSON-RPC"
        else:
            raw_cli = CISCO_NEXUS_BEFORE_CLI if phase == "pre_change" else CISCO_NEXUS_AFTER_CLI
            routes = await asyncio.to_thread(parse_cisco_nxos_cli, raw_cli, self.hostname)
            notes = f"Collected via simulated NX-OS transport + production NX-OS parser (phase={phase})"

        unique_prefixes = len({(r.vrf, r.prefix) for r in routes})
        return DeviceFetchResult(
            device_id=self.device_id,
            hostname=self.hostname,
            ip_address=self.ip_address,
            device_type="cisco_nexus",
            routes=routes,
            raw_entry_count=len(routes),
            unique_prefix_count=unique_prefixes,
            collector_notes=notes,
        )

    async def _collect_live_nxapi(self):
        username = str(self.config_json.get("username") or "")
        password = str(self.config_json.get("password") or "")
        scheme = "https" if self.config_json.get("use_https", True) else "http"
        url = f"{scheme}://{self.ip_address}/ins"
        body = {
            "ins_api": {
                "version": "1.0",
                "type": "cli_show",
                "chunk": "0",
                "sid": "1",
                "input": "show ip route vrf all",
                "output_format": "json",
            }
        }
        async with httpx.AsyncClient(
            auth=(username, password),
            timeout=20.0,
            verify=bool(self.config_json.get("verify_ssl", False)),
        ) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            payload = resp.json().get("ins_api", {}).get("outputs", {}).get("output", {}).get("body", {})
            return parse_cisco_nxapi_json(payload, hostname=self.hostname)
