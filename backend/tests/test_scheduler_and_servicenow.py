"""Tests for ServiceNow sync, dynamic T-1h rescheduling, cancellation, and due-job claiming."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.concurrency import PipelineExecutor
from app.core.config import Settings
from app.models.entities import ChangeRequest, Device, MockServiceNowChange
from app.scheduler.jobs import SchedulerManager
from app.services.change_service import ChangeWorkflowService


@pytest.mark.asyncio
async def test_servicenow_sync_reschedule_and_due_dispatch(
    test_settings: Settings,
    db_session_factory,
):
    _, factory = db_session_factory
    executor = PipelineExecutor(mode="sync")
    service = ChangeWorkflowService(settings=test_settings, pipeline_executor=executor)
    scheduler = SchedulerManager(
        settings=test_settings,
        session_factory=factory,
        change_service=service,
    )

    # 1. Initial sync pulls the 2 seeded ServiceNow changes
    synced_count = await scheduler.run_sync_tick()
    assert synced_count == 2

    with factory() as db:
        chg_due = db.scalar(select(ChangeRequest).where(ChangeRequest.chg_number == "CHG0042108"))
        chg_future = db.scalar(select(ChangeRequest).where(ChangeRequest.chg_number == "CHG0042115"))
        assert chg_due is not None and chg_due.status == "synced"
        assert chg_future is not None and chg_future.status == "synced"

    # 2. Dispatch tick claims ONLY CHG0042108 (starts in 45m -> T-1h already passed),
    # NOT CHG0042115 (starts in 4h)
    processed = await scheduler.run_dispatch_tick()
    assert len(processed) == 1

    with factory() as db:
        chg_due = db.scalar(select(ChangeRequest).where(ChangeRequest.chg_number == "CHG0042108"))
        chg_future = db.scalar(select(ChangeRequest).where(ChangeRequest.chg_number == "CHG0042115"))
        assert chg_due.status == "pre_captured"
        assert chg_future.status == "synced"

    # 3. Reschedule CHG0042115 in simulated ServiceNow to 30m from now -> sync updates capture_scheduled_at
    with factory() as db:
        snow_future = db.scalar(
            select(MockServiceNowChange).where(MockServiceNowChange.chg_number == "CHG0042115")
        )
        snow_future.scheduled_start = datetime.now(UTC) + timedelta(minutes=30)
        db.commit()

    await scheduler.run_sync_tick()
    processed_second = await scheduler.run_dispatch_tick()
    assert len(processed_second) == 1

    # 4. Create a new change and then cancel it in ServiceNow -> status transitions to cancelled
    with factory() as db:
        dev = db.scalar(select(Device).limit(1))
        snow_cancel = MockServiceNowChange(
            chg_number="CHG0099999",
            title="Temporary Change To Cancel",
            scheduled_start=datetime.now(UTC) + timedelta(hours=5),
            engineer_name="Test Eng",
            engineer_email="test@netops.local",
            state="scheduled",
            ci_device_ids=[dev.id],
        )
        db.add(snow_cancel)
        db.commit()

    await scheduler.run_sync_tick()
    with factory() as db:
        snow_cancel = db.scalar(
            select(MockServiceNowChange).where(MockServiceNowChange.chg_number == "CHG0099999")
        )
        snow_cancel.state = "cancelled"
        db.commit()

    await scheduler.run_sync_tick()
    with factory() as db:
        synced_cancel = db.scalar(select(ChangeRequest).where(ChangeRequest.chg_number == "CHG0099999"))
        assert synced_cancel is not None
        assert synced_cancel.status == "cancelled"
