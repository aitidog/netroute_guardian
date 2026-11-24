"""Pydantic v2 DTO schemas for all REST endpoints."""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_address(value: str) -> str:
    """Validate email syntax while permitting internal/local domains (e.g. .local, .corp)."""
    cleaned = value.strip()
    if not _EMAIL_RE.match(cleaned):
        raise ValueError("Must be a valid email address")
    return cleaned


def normalize_cidr(value: str) -> str:
    """Validate and canonicalize an IPv4/IPv6 CIDR string."""
    cleaned = value.strip()
    if not cleaned or "/" not in cleaned:
        raise ValueError("Route entry must be a valid CIDR prefix (e.g. 10.76.12.0/23)")
    net = ipaddress.ip_network(cleaned, strict=False)
    return str(net)


# ---------------------------------------------------------------------------
# Device schemas
# ---------------------------------------------------------------------------
class DeviceCreate(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=128)
    ip_address: str = Field(..., min_length=1, max_length=64)
    device_type: Literal["edgeconnect", "cisco_nexus", "cisco_router"]
    connection_mode: Literal["mock", "live"] = "mock"
    location: str = ""
    description: str = ""
    config_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        ipaddress.ip_address(value.strip())
        return value.strip()


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str
    ip_address: str
    device_type: str
    connection_mode: str
    location: str
    description: str
    config_json: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Important route rule schemas
# ---------------------------------------------------------------------------
class ImportantRouteCreate(BaseModel):
    prefix: str = Field(..., examples=["10.76.12.0/23"])
    description: str = Field(default="", max_length=255)
    enabled: bool = True

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        return normalize_cidr(value)


class ImportantRouteUpdate(BaseModel):
    prefix: str | None = None
    description: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str | None) -> str | None:
        return normalize_cidr(value) if value is not None else None


class ImportantRouteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prefix: str
    description: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Mock ServiceNow schemas
# ---------------------------------------------------------------------------
class MockServiceNowChangeCreate(BaseModel):
    chg_number: str | None = Field(default=None, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    scheduled_start: datetime
    scheduled_end: datetime | None = None
    engineer_name: str = Field(..., min_length=1, max_length=128)
    engineer_email: str = Field(..., min_length=3, max_length=255)
    state: Literal["scheduled", "implement", "closed", "cancelled"] = "scheduled"
    ci_device_ids: list[int] = Field(..., min_length=1)

    @field_validator("engineer_email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return validate_email_address(value)


class MockServiceNowChangeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    engineer_name: str | None = None
    engineer_email: str | None = Field(default=None, min_length=3, max_length=255)
    state: Literal["scheduled", "implement", "closed", "cancelled"] | None = None
    ci_device_ids: list[int] | None = None

    @field_validator("engineer_email")
    @classmethod
    def check_email(cls, value: str | None) -> str | None:
        return validate_email_address(value) if value is not None else None


class MockServiceNowChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chg_number: str
    title: str
    description: str
    scheduled_start: datetime
    scheduled_end: datetime | None
    engineer_name: str
    engineer_email: str
    state: str
    ci_device_ids: list[int]
    updated_at: datetime


# ---------------------------------------------------------------------------
# Change request, snapshot, and comparison report schemas
# ---------------------------------------------------------------------------
class SnapshotSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int | None
    change_id: int | None
    device_label: str
    phase: str
    source_type: str
    raw_entry_count: int
    unique_prefix_count: int
    captured_at: datetime


class ComparisonReportSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    change_id: int | None
    device_id: int | None
    device_label: str
    before_snapshot_id: int
    after_snapshot_id: int
    risk_level: str
    summary_stats: dict[str, Any]
    email_recipient: str | None
    email_status: str
    email_error: str | None
    email_sent_at: datetime | None
    created_at: datetime


class ComparisonReportDetailRead(ComparisonReportSummaryRead):
    report_payload: dict[str, Any]


class ChangeRequestRead(BaseModel):
    id: int
    chg_number: str
    title: str
    description: str
    scheduled_start: datetime
    scheduled_end: datetime | None
    capture_scheduled_at: datetime
    engineer_name: str
    engineer_email: str
    status: str
    sync_source: str
    retry_count: int
    last_error: str | None
    synced_at: datetime
    updated_at: datetime
    devices: list[DeviceRead] = Field(default_factory=list)
    pre_snapshot_count: int = 0
    post_snapshot_count: int = 0
    report_count: int = 0
    highest_risk_level: str | None = None


class ChangeRequestDetailRead(ChangeRequestRead):
    snapshots: list[SnapshotSummaryRead] = Field(default_factory=list)
    reports: list[ComparisonReportDetailRead] = Field(default_factory=list)


class TriggerCaptureResult(BaseModel):
    change_id: int
    chg_number: str
    phase: str
    succeeded_devices: list[str]
    failed_devices: list[dict[str, str]]
    reports_generated: list[ComparisonReportSummaryRead] = Field(default_factory=list)
    email_status: str | None = None


# ---------------------------------------------------------------------------
# Route summary (Feature 2) schemas
# ---------------------------------------------------------------------------
class RouteSummaryDeviceRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Device IP address or hostname")
    include_supernet_suggestions: bool = False


class RouteSummaryTextRequest(BaseModel):
    raw_text: str = Field(..., min_length=1)
    source_label: str = "Manual Input"
    include_supernet_suggestions: bool = False


class RouteSummaryResponse(BaseModel):
    source_label: str
    device_type: str | None = None
    device_ip: str | None = None
    total_raw_entries: int
    total_unique_prefixes: int
    ignored_default_routes: int
    output_route_count: int
    summary_route_count: int
    remaining_route_count: int
    covered_route_count: int
    compression_ratio_pct: float
    vrf_groups: list[dict[str, Any]]
    summary_routes: list[dict[str, Any]]
    remaining_routes: list[dict[str, Any]]
    all_output_routes: list[dict[str, Any]]
    supernet_suggestions: list[dict[str, Any]] | None = None
    pipeline_stages: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Settings and scheduler status schemas
# ---------------------------------------------------------------------------
class AppSettingsRead(BaseModel):
    servicenow_mode: str
    servicenow_window_hours: int
    pre_capture_lead_minutes: int
    large_prefix_threshold: int
    max_concurrent_device_collections: int
    pipeline_executor_mode: str
    pipeline_max_workers: int
    mailpit_web_url: str


class AppSettingsUpdate(BaseModel):
    servicenow_window_hours: int | None = Field(default=None, ge=1, le=720)
    pre_capture_lead_minutes: int | None = Field(default=None, ge=1, le=1440)
    large_prefix_threshold: int | None = Field(default=None, ge=1, le=32)


class SchedulerStatusRead(BaseModel):
    running: bool
    servicenow_mode: str
    last_sync_at: datetime | None
    last_dispatch_at: datetime | None
    synced_changes_count: int
    pending_pre_captures: int
    next_due_capture_at: datetime | None
    jobs: list[dict[str, Any]]
