"""Tests for Jinja2 HTML comparison report email rendering and SMTP delivery handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.email.sender import EmailReportSender
from app.core.config import Settings
from app.pipelines.comparison.context import ComparisonInput
from app.pipelines.comparison.pipeline import run_comparison_pipeline


def _sample_report() -> dict:
    return run_comparison_pipeline(
        ComparisonInput(
            device_label="uec-abc-prd01",
            before_routes=[
                {"prefix": "10.132.0.0/14", "vrf": "default", "metric": 50, "admin_distance": 15},
                {"prefix": "10.76.12.0/23", "vrf": "default", "metric": 50, "admin_distance": 15},
            ],
            after_routes=[
                {"prefix": "10.156.43.128/25", "vrf": "default", "metric": 50, "admin_distance": 15},
            ],
            important_prefixes=["10.76.12.0/23"],
            large_prefix_threshold=20,
        )
    )


def test_email_html_rendering_contains_important_and_normal_sections(test_settings: Settings):
    sender = EmailReportSender(test_settings)
    subject, html = sender.render_html(
        chg_number="CHG0042108",
        change_title="SD-WAN Policy Cutover",
        engineer_name="Alex Rivera",
        recipient_email="alex.rivera@netops.local",
        reports=[_sample_report()],
    )
    assert "[CRITICAL]" in subject
    assert "CHG0042108" in subject
    assert "10.132.0.0/14" in html
    assert "10.76.12.0/23" in html
    assert "10.156.43.128/25" in html
    assert "Emphasized Important Routing Differences" in html


@pytest.mark.asyncio
async def test_email_sender_dispatches_via_aiosmtplib(test_settings: Settings):
    smtp_settings = test_settings.model_copy(update={"smtp_enabled": True})
    sender = EmailReportSender(smtp_settings)

    with patch("app.adapters.email.sender.aiosmtplib.send", new=AsyncMock()) as mock_send:
        result = await sender.send_comparison_report(
            chg_number="CHG0042108",
            change_title="SD-WAN Policy Cutover",
            engineer_name="Alex Rivera",
            recipient_email="alex.rivera@netops.local",
            reports=[_sample_report()],
        )
        assert result.status == "sent"
        assert mock_send.await_count == 1
        sent_msg = mock_send.await_args.args[0]
        assert sent_msg["To"] == "alex.rivera@netops.local"
        assert "CHG0042108" in sent_msg["Subject"]
