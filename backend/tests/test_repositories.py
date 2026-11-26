"""Direct unit tests for the SQLAlchemy Repository layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.repositories.bundle import RepositoryBundle


@pytest.mark.asyncio
async def test_device_and_important_route_repositories(db_session):
    repos = RepositoryBundle(db_session)

    # Case-insensitive hostname and exact IP lookup
    by_host = await repos.devices.get_by_hostname_or_ip("UEC-ABC-PRD01")
    by_ip = await repos.devices.get_by_hostname_or_ip("10.162.183.10")
    assert by_host is not None and by_ip is not None
    assert by_host.id == by_ip.id

    # Duplicate device raises domain ConflictError (not raw SQLAlchemy IntegrityError)
    with pytest.raises(ConflictError):
        await repos.devices.create(
            hostname="uec-abc-prd01",
            ip_address="10.99.99.99",
            device_type="edgeconnect",
        )

    # Important route create -> update -> delete -> missing raises ResourceNotFoundError
    created = await repos.important_routes.create(
        prefix="10.222.0.0/16",
        description="Repo test route",
        enabled=True,
    )
    assert "10.222.0.0/16" in await repos.important_routes.list_enabled_prefixes()

    updated = await repos.important_routes.update(created.id, enabled=False)
    assert updated.enabled is False
    assert "10.222.0.0/16" not in await repos.important_routes.list_enabled_prefixes()

    await repos.important_routes.delete(created.id)
    with pytest.raises(ResourceNotFoundError):
        await repos.important_routes.delete(created.id)


@pytest.mark.asyncio
async def test_settings_and_change_claiming_repositories(db_session):
    repos = RepositoryBundle(db_session)

    await repos.settings.upsert_many({"large_prefix_threshold": "18"})
    assert await repos.settings.get_int("large_prefix_threshold", 20) == 18

    now = datetime.now(UTC)
    chg = await repos.changes.create(
        chg_number="CHG_REPO_001",
        title="Repo Claim Test",
        description="",
        scheduled_start=now + timedelta(minutes=30),
        scheduled_end=None,
        capture_scheduled_at=now - timedelta(minutes=30),
        engineer_name="Test",
        engineer_email="test@netops.local",
        status="synced",
        sync_source="mock",
        synced_at=now,
    )
    await repos.commit()

    claimed = await repos.changes.claim_due_pre_capture_ids(now)
    assert chg.id in claimed
    # Claiming again is idempotent (already transitioned to pre_capturing)
    claimed_again = await repos.changes.claim_due_pre_capture_ids(now)
    assert chg.id not in claimed_again
