"""Tests for Jinja2 HTML comparison report email rendering and SMTP delivery handling."""

from __future__ import annotations

import csv
import io
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.email.csv_exporter import CSV_HEADERS, format_comparison_reports_csv
from app.adapters.email.sender import EmailReportSender
from app.core.config import Settings
from app.pipelines.comparison.context import ComparisonInput
from app.pipelines.comparison.pipeline import run_comparison_pipeline


def _sample_report() -> dict:
    return run_comparison_pipeline(
        ComparisonInput(
            device_label="uec-abc-prd01",
            before_routes=[
                {
                    "prefix": "10.132.0.0/14",
                    "vrf": "default",
                    "metric": 50,
                    "admin_distance": 15,
                    "raw_metric": "50 (AD:15)",
                },
                {
                    "prefix": "10.132.0.0/14",
                    "vrf": "default",
                    "metric": 100,
                    "admin_distance": 15,
                    "raw_metric": "100 (AD:15)",
                },
                {
                    "prefix": "10.76.12.0/23",
                    "vrf": "default",
                    "metric": 50,
                    "admin_distance": 15,
                    "raw_metric": "50 (AD:15)",
                },
            ],
            after_routes=[
                {
                    "prefix": "10.156.43.128/25",
                    "vrf": "default",
                    "metric": 50,
                    "admin_distance": 15,
                    "raw_metric": "50 (AD:15)",
                },
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
async def test_email_sender_dispatches_via_aiosmtplib_with_csv_attachment(test_settings: Settings):
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
        assert result.csv_filename == "route-comparison-CHG0042108.csv"
        assert mock_send.await_count == 1

        sent_msg = mock_send.await_args.args[0]
        assert sent_msg["To"] == "alex.rivera@netops.local"
        assert "CHG0042108" in sent_msg["Subject"]

        attachments = list(sent_msg.iter_attachments())
        assert len(attachments) == 1
        att = attachments[0]
        assert att.get_filename() == "route-comparison-CHG0042108.csv"
        assert att.get_content_type() == "text/csv"

        csv_body = att.get_payload(decode=True).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(csv_body)))
        # 2 removed entries for 10.132.0.0/14 + 1 removed for 10.76.12.0/23 + 1 added for 10.156.43.128/25
        assert len(rows) == 4
        assert {r["Subnet/Mask"] for r in rows} == {"10.132.0.0/14", "10.76.12.0/23", "10.156.43.128/25"}
        assert (
            sum(1 for r in rows if r["Subnet/Mask"] == "10.132.0.0/14" and r["Entry_Action"] == "REMOVED")
            == 2
        )


def test_format_comparison_reports_csv_headers_and_values():
    csv_text = format_comparison_reports_csv([_sample_report()])
    reader = csv.reader(io.StringIO(csv_text))
    headers = next(reader)
    assert headers == CSV_HEADERS
    rows = list(reader)
    assert len(rows) == 4
    assert rows[0][0] == "uec-abc-prd01"
