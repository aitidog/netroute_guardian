"""Jinja2 HTML email renderer and async SMTP sender (compatible with Mailpit and enterprise SMTP)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.adapters.email.csv_exporter import format_comparison_reports_csv, sanitize_filename_token
from app.core.config import Settings

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@dataclass
class EmailDeliveryResult:
    status: str  # sent | failed | skipped
    error: str | None = None
    subject: str = ""
    html_body: str = ""
    csv_filename: str = ""
    csv_content: str = ""


class EmailReportSender:
    """Renders structured comparison reports into HTML emails and dispatches them via SMTP."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jinja = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_html(
        self,
        *,
        chg_number: str,
        change_title: str,
        engineer_name: str,
        recipient_email: str,
        reports: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Return ``(subject, html_body)`` for one or more device comparison reports."""
        total_important_alerts = sum(
            int((r.get("summary_stats") or {}).get("important_count", 0)) for r in reports
        )
        total_differences = sum(
            int((r.get("summary_stats") or {}).get("total_differences", 0)) for r in reports
        )

        if total_important_alerts > 0:
            subject_tag = f"IMPORTANT: {total_important_alerts} Alert(s)"
        elif total_differences > 0:
            subject_tag = f"{total_differences} Diff(s)"
        else:
            subject_tag = "No Differences"

        device_names = ", ".join(str(r.get("device_label", "")) for r in reports)
        subject = f"[{subject_tag}] Route Comparison Report — {chg_number} ({device_names})"
        csv_filename = f"route-comparison-{sanitize_filename_token(chg_number)}.csv"

        template = self._jinja.get_template("comparison_report.html")
        html_body = template.render(
            chg_number=chg_number,
            change_title=change_title,
            engineer_name=engineer_name,
            recipient_email=recipient_email,
            total_important_alerts=total_important_alerts,
            reports=reports,
            csv_filename=csv_filename,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        return subject, html_body

    async def send_comparison_report(
        self,
        *,
        chg_number: str,
        change_title: str,
        engineer_name: str,
        recipient_email: str,
        reports: list[dict[str, Any]],
    ) -> EmailDeliveryResult:
        """Render and send the HTML report email with a CSV diff attachment to the engineer."""
        subject, html_body = self.render_html(
            chg_number=chg_number,
            change_title=change_title,
            engineer_name=engineer_name,
            recipient_email=recipient_email,
            reports=reports,
        )
        csv_filename = f"route-comparison-{sanitize_filename_token(chg_number)}.csv"
        csv_content = format_comparison_reports_csv(reports)

        if not self.settings.smtp_enabled:
            return EmailDeliveryResult(
                status="skipped",
                subject=subject,
                html_body=html_body,
                csv_filename=csv_filename,
                csv_content=csv_content,
            )

        msg = EmailMessage()
        msg["From"] = self.settings.smtp_from_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.set_content(
            f"Routing table comparison report for {chg_number} ({change_title}). "
            f"A structured CSV export ({csv_filename}) is attached. "
            "Please view this email in an HTML-capable client for the formatted summary."
        )
        msg.add_alternative(html_body, subtype="html")
        # Include UTF-8 BOM in attached CSV so Excel renders special characters cleanly.
        msg.add_attachment(
            ("\ufeff" + csv_content).encode("utf-8"),
            maintype="text",
            subtype="csv",
            filename=csv_filename,
        )

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                username=self.settings.smtp_username or None,
                password=self.settings.smtp_password or None,
                start_tls=self.settings.smtp_use_tls,
                timeout=10.0,
            )
            logger.info("Sent route comparison email for %s to %s", chg_number, recipient_email)
            return EmailDeliveryResult(
                status="sent",
                subject=subject,
                html_body=html_body,
                csv_filename=csv_filename,
                csv_content=csv_content,
            )
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", recipient_email, exc)
            return EmailDeliveryResult(
                status="failed",
                error=str(exc),
                subject=subject,
                html_body=html_body,
                csv_filename=csv_filename,
                csv_content=csv_content,
            )
