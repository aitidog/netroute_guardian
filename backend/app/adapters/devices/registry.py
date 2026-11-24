"""Device collector factory and bounded-concurrency multi-device orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.adapters.devices.base import DeviceCollector, DeviceFetchResult
from app.adapters.devices.cisco_nexus import CiscoNexusCollector
from app.adapters.devices.cisco_router import CiscoRouterCollector
from app.adapters.devices.edgeconnect import EdgeConnectCollector
from app.core.concurrency import gather_with_concurrency
from app.models.entities import Device


def build_device_collector(device: Device, sample_data_dir: str) -> DeviceCollector:
    """Instantiate the appropriate vendor DeviceCollector for an ORM Device record."""
    if device.device_type == "edgeconnect":
        return EdgeConnectCollector(
            device_id=device.id,
            hostname=device.hostname,
            ip_address=device.ip_address,
            connection_mode=device.connection_mode,
            config_json=device.config_json,
            sample_data_dir=sample_data_dir,
        )
    if device.device_type == "cisco_nexus":
        return CiscoNexusCollector(
            device_id=device.id,
            hostname=device.hostname,
            ip_address=device.ip_address,
            connection_mode=device.connection_mode,
            config_json=device.config_json,
        )
    if device.device_type == "cisco_router":
        return CiscoRouterCollector(
            device_id=device.id,
            hostname=device.hostname,
            ip_address=device.ip_address,
            connection_mode=device.connection_mode,
            config_json=device.config_json,
        )
    raise ValueError(f"Unsupported device_type: {device.device_type}")


@dataclass
class BatchCollectionOutcome:
    """Aggregated outcome of concurrent multi-device route collection."""

    succeeded: list[DeviceFetchResult]
    failed: list[dict[str, str]]


class ConcurrentDeviceCollector:
    """Collects routing tables across multiple devices concurrently with semaphore & timeout bounds."""

    def __init__(
        self,
        *,
        sample_data_dir: str,
        max_concurrency: int = 10,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.sample_data_dir = sample_data_dir
        self.max_concurrency = max(1, max_concurrency)
        self.timeout_seconds = timeout_seconds

    async def collect_many(
        self,
        devices: list[Device],
        phase: Literal["pre_change", "post_change", "adhoc"] = "adhoc",
        collector_factory=build_device_collector,
    ) -> BatchCollectionOutcome:
        """Fetch routing tables from all provided devices concurrently with failure isolation."""
        if not devices:
            return BatchCollectionOutcome(succeeded=[], failed=[])

        coros = [collector_factory(dev, self.sample_data_dir).collect_routes(phase=phase) for dev in devices]
        raw_results = await gather_with_concurrency(
            limit=self.max_concurrency,
            coros=coros,
            timeout_seconds=self.timeout_seconds,
        )

        succeeded: list[DeviceFetchResult] = []
        failed: list[dict[str, str]] = []
        for dev, outcome in zip(devices, raw_results, strict=True):
            if isinstance(outcome, BaseException):
                failed.append(
                    {
                        "hostname": dev.hostname,
                        "ip_address": dev.ip_address,
                        "error": f"{type(outcome).__name__}: {outcome}",
                    }
                )
            else:
                succeeded.append(outcome)

        return BatchCollectionOutcome(succeeded=succeeded, failed=failed)
