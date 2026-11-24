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

from app.core.config import Settings

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_RISK_RANK = {"PASS": 0, "INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}


@dataclass
class EmailDeliveryResult:
    status: str  # sent | failed | skipped
    error: str | None = None
    subject: str = ""
    html_body: str = ""


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
        overall_risk = "PASS"
        for rep in reports:
            level = str(rep.get("risk_level") or "PASS")
            if _RISK_RANK.get(level, 0) > _RISK_RANK.get(overall_risk, 0):
                overall_risk = level

        device_names = ", ".join(str(r.get("device_label", "")) for r in reports)
        subject = f"[{overall_risk}] Route Comparison Report — {chg_number} ({device_names})"

        template = self._jinja.get_template("comparison_report.html")
        html_body = template.render(
            chg_number=chg_number,
            change_title=change_title,
            engineer_name=engineer_name,
            recipient_email=recipient_email,
            overall_risk=overall_risk,
            reports=reports,
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
        """Render and send the HTML report email to the engineer's mailbox."""
        subject, html_body = self.render_html(
            chg_number=chg_number,
            change_title=change_title,
            engineer_name=engineer_name,
            recipient_email=recipient_email,
            reports=reports,
        )

        if not self.settings.smtp_enabled:
            return EmailDeliveryResult(
                status="skipped",
                subject=subject,
                html_body=html_body,
            )

        msg = EmailMessage()
        msg["From"] = self.settings.smtp_from_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.set_content(
            f"Routing table comparison report for {chg_number} ({change_title}). "
            "Please view this email in an HTML-capable client."
        )
        msg.add_alternative(html_body, subtype="html")

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
            return EmailDeliveryResult(status="sent", subject=subject, html_body=html_body)
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", recipient_email, exc)
            return EmailDeliveryResult(
                status="failed",
                error=str(exc),
                subject=subject,
                html_body=html_body,
            )
