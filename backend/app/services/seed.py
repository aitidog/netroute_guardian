"""Idempotent database seeding for demo devices, important routes, settings, and ServiceNow changes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import (
    AppSetting,
    Device,
    ImportantRoute,
    MockServiceNowChange,
)

DEFAULT_IMPORTANT_ROUTES = [
    ("0.0.0.0/0", "Default gateway / Internet & WAN fallback route"),
    ("10.76.12.0/23", "Core regional application subnet (pre-specified critical)"),
    ("10.127.0.0/16", "Primary data center transit block (pre-specified critical)"),
    ("10.130.0.0/17", "Secondary data center production block (pre-specified critical)"),
]


def seed_initial_data(db: Session, settings: Settings) -> None:
    """Seed default settings, critical route rules, multi-vendor devices, and sample changes."""
    # 1. Runtime settings
    default_settings = {
        "servicenow_window_hours": (
            str(settings.servicenow_window_hours),
            "Lookahead window (hours) when polling scheduled ServiceNow network changes",
        ),
        "pre_capture_lead_minutes": (
            str(settings.pre_capture_lead_minutes),
            "Minutes before scheduled_start to automatically capture pre-change routing tables",
        ),
        "large_prefix_threshold": (
            str(settings.default_large_prefix_threshold),
            "CIDR prefix length threshold (<= /N) flagged as high-priority when missing or changed",
        ),
    }
    for key, (val, desc) in default_settings.items():
        if db.get(AppSetting, key) is None:
            db.add(AppSetting(key=key, value=val, description=desc))

    # 2. Pre-specified important routes from requirements
    for prefix, desc in DEFAULT_IMPORTANT_ROUTES:
        exists = db.scalar(select(ImportantRoute).where(ImportantRoute.prefix == prefix))
        if exists is None:
            db.add(ImportantRoute(prefix=prefix, description=desc, enabled=True))

    # 3. Three multi-vendor demo devices (EdgeConnect CSV + Cisco Nexus + Cisco Router)
    demo_devices = [
        {
            "hostname": "uec-abc-prd01",
            "ip_address": "10.162.183.10",
            "device_type": "edgeconnect",
            "connection_mode": "mock",
            "location": "US-East Primary SD-WAN Hub",
            "description": (
                "Aruba EdgeConnect SD-WAN appliance backed by the provided "
                "subnetsExample_beforeChange.csv / subnetsExample_afterChange.csv fixtures"
            ),
            "config_json": {
                "before_csv": "subnetsExample_beforeChange.csv",
                "after_csv": "subnetsExample_afterChange.csv",
            },
        },
        {
            "hostname": "nx-dc1-core01",
            "ip_address": "10.0.1.11",
            "device_type": "cisco_nexus",
            "connection_mode": "mock",
            "location": "DC1 Core Switch Fabric",
            "description": ("Cisco Nexus 9000 switch parsed through the production NX-OS CLI parser"),
            "config_json": {},
        },
        {
            "hostname": "rtr-hq-wan01",
            "ip_address": "10.0.1.21",
            "device_type": "cisco_router",
            "connection_mode": "mock",
            "location": "HQ WAN Border Router",
            "description": ("Cisco IOS-XE WAN router parsed through the production IOS-XE CLI parser"),
            "config_json": {},
        },
    ]

    device_by_host: dict[str, Device] = {}
    for spec in demo_devices:
        dev = db.scalar(select(Device).where(Device.hostname == spec["hostname"]))
        if dev is None:
            dev = Device(**spec)
            db.add(dev)
            db.flush()
        device_by_host[spec["hostname"]] = dev

    # 4. Seed realistic simulated ServiceNow Change Requests if none exist yet
    existing_snow = db.scalar(select(MockServiceNowChange.id).limit(1))
    if existing_snow is None:
        now = datetime.now(UTC)
        ec_id = device_by_host["uec-abc-prd01"].id
        nx_id = device_by_host["nx-dc1-core01"].id
        rtr_id = device_by_host["rtr-hq-wan01"].id

        # Change 1: Scheduled 45 minutes from now -> T-1h pre-capture is already due on startup!
        db.add(
            MockServiceNowChange(
                chg_number="CHG0042108",
                title="SD-WAN Hub & Core BGP Route Policy Cutover",
                description=(
                    "Scheduled WAN routing policy update across Aruba EdgeConnect hub "
                    "uec-abc-prd01 and DC1 Cisco Nexus core nx-dc1-core01."
                ),
                scheduled_start=now + timedelta(minutes=45),
                scheduled_end=now + timedelta(hours=2, minutes=45),
                engineer_name="Alex Rivera",
                engineer_email="alex.rivera@netops.local",
                state="scheduled",
                ci_device_ids=[ec_id, nx_id],
            )
        )
        # Change 2: Scheduled 4 hours from now -> T-1h countdown visible in UI (3h remaining)
        db.add(
            MockServiceNowChange(
                chg_number="CHG0042115",
                title="HQ WAN Router BGP Local-Pref & Failover Maintenance",
                description=(
                    "Planned BGP preference maintenance on HQ border router rtr-hq-wan01 "
                    "and EdgeConnect hub uec-abc-prd01."
                ),
                scheduled_start=now + timedelta(hours=4),
                scheduled_end=now + timedelta(hours=6),
                engineer_name="Jordan Chen",
                engineer_email="jordan.chen@netops.local",
                state="scheduled",
                ci_device_ids=[rtr_id, ec_id],
            )
        )

    db.commit()
