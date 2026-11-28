"""Idempotent database seeding routed strictly through the Repository layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.repositories.bundle import RepositoryBundle

DEFAULT_IMPORTANT_ROUTES = [
    ("0.0.0.0/0", "Default gateway / Internet & WAN fallback route"),
    ("10.76.12.0/23", "Core regional application subnet (pre-specified critical)"),
    ("10.127.0.0/16", "Primary data center transit block (pre-specified critical)"),
    ("10.130.0.0/17", "Secondary data center production block (pre-specified critical)"),
]


async def seed_initial_data(repos: RepositoryBundle, settings: Settings) -> None:
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
        await repos.settings.ensure_default(key=key, value=val, description=desc)

    # 2. Pre-specified important routes from requirements
    for prefix, desc in DEFAULT_IMPORTANT_ROUTES:
        if await repos.important_routes.get_by_prefix(prefix) is None:
            await repos.important_routes.create(prefix=prefix, description=desc, enabled=True, commit=False)

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

    device_ids_by_host: dict[str, int] = {}
    for spec in demo_devices:
        dev = await repos.devices.get_by_hostname(spec["hostname"])
        if dev is None:
            dev = await repos.devices.create(**spec, commit=False)
        device_ids_by_host[spec["hostname"]] = dev.id

    # 4. Seed realistic simulated ServiceNow Change Requests if none exist yet
    if not await repos.mock_servicenow.has_any():
        now = datetime.now(UTC)
        ec_id = device_ids_by_host["uec-abc-prd01"]

        await repos.mock_servicenow.create(
            chg_number="CHG0042108",
            title="SD-WAN Hub Route Policy Cutover (uec-abc-prd01)",
            description=(
                "Scheduled WAN routing policy update on Aruba EdgeConnect hub uec-abc-prd01."
            ),
            scheduled_start=now + timedelta(minutes=45),
            scheduled_end=now + timedelta(hours=2, minutes=45),
            engineer_name="Alex Rivera",
            engineer_email="alex.rivera@netops.local",
            state="scheduled",
            ci_device_ids=[ec_id],
            commit=False,
        )
        await repos.mock_servicenow.create(
            chg_number="CHG0042115",
            title="SD-WAN Hub BGP Preference Maintenance (uec-abc-prd01)",
            description=(
                "Planned routing preference maintenance on Aruba EdgeConnect hub uec-abc-prd01."
            ),
            scheduled_start=now + timedelta(hours=4),
            scheduled_end=now + timedelta(hours=6),
            engineer_name="Jordan Chen",
            engineer_email="jordan.chen@netops.local",
            state="scheduled",
            ci_device_ids=[ec_id],
            commit=False,
        )

    await repos.commit()
