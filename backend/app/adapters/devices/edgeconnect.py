"""Silver Peak / Aruba EdgeConnect device collector (live Orchestrator REST + mock CSV)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

import httpx

from app.adapters.devices.base import DeviceCollector, DeviceFetchResult
from app.adapters.devices.parsers import (
    parse_edgeconnect_csv,
    parse_edgeconnect_orchestrator_json,
)


class EdgeConnectCollector(DeviceCollector):
    """Collects routing tables from Silver Peak / Aruba EdgeConnect SD-WAN appliances."""

    def __init__(
        self,
        *,
        device_id: int | None,
        hostname: str,
        ip_address: str,
        connection_mode: str = "mock",
        config_json: dict | None = None,
        sample_data_dir: str = "",
    ) -> None:
        self.device_id = device_id
        self.hostname = hostname
        self.ip_address = ip_address
        self.connection_mode = connection_mode
        self.config_json = config_json or {}
        self.sample_data_dir = sample_data_dir

    async def collect_routes(
        self,
        phase: Literal["pre_change", "post_change", "adhoc"] = "adhoc",
    ) -> DeviceFetchResult:
        if self.connection_mode == "live":
            routes = await self._collect_live()
            notes = "Collected via Aruba Orchestrator REST API"
        else:
            routes = await self._collect_mock(phase)
            notes = f"Collected via EdgeConnect CSV simulator (phase={phase})"

        unique_prefixes = len({(r.vrf, r.prefix) for r in routes})
        return DeviceFetchResult(
            device_id=self.device_id,
            hostname=self.hostname,
            ip_address=self.ip_address,
            device_type="edgeconnect",
            routes=routes,
            raw_entry_count=len(routes),
            unique_prefix_count=unique_prefixes,
            collector_notes=notes,
        )

    async def _collect_mock(self, phase: str):
        filename = (
            self.config_json.get("before_csv", "subnetsExample_beforeChange.csv")
            if phase == "pre_change"
            else self.config_json.get("after_csv", "subnetsExample_afterChange.csv")
        )
        csv_path = Path(self.sample_data_dir) / filename
        # Offload file read + CSV parsing to a worker thread so the asyncio loop stays responsive.
        csv_text = await asyncio.to_thread(csv_path.read_text, encoding="utf-8-sig")
        return await asyncio.to_thread(parse_edgeconnect_csv, csv_text)

    async def _collect_live(self):
        orchestrator_url = str(self.config_json.get("orchestrator_url") or "").rstrip("/")
        ne_pk = str(self.config_json.get("ne_pk") or "")
        api_key = str(self.config_json.get("api_key") or "")
        if not orchestrator_url or not ne_pk:
            raise ValueError(
                f"Live EdgeConnect device {self.hostname} requires 'orchestrator_url' and 'ne_pk'"
            )
        headers = {"Accept": "application/json"}
        if api_key:
            headers["X-Auth-Token"] = api_key
        async with httpx.AsyncClient(
            base_url=orchestrator_url,
            headers=headers,
            timeout=20.0,
            verify=bool(self.config_json.get("verify_ssl", True)),
        ) as client:
            resp = await client.get(f"/gms/rest/subnets/appliance/{ne_pk}")
            resp.raise_for_status()
            return parse_edgeconnect_orchestrator_json(resp.json(), appliance=self.hostname)
