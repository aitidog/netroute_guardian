"""Canonical entry-level CSV exporter for Feature 1 routing table comparison reports.

Expands every prefix diff to individual route-entry (path) granularity matching the
row-by-row structure of raw EdgeConnect / Cisco routing tables.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

CSV_HEADERS = [
    "Appliance",
    "Subnet/Mask",
    "Next Hop",
    "Interface",
    "Metric",
    "Admin_Distance",
    "Metric_Value",
    "Peer_Priority",
    "Prefix_Change_Type",
    "Entry_Action",
    "Is_Important",
    "Matched_Rules",
    "Importance_Reasons",
    "Prefix_Entries_Before",
    "Prefix_Entries_After",
    "Prefix_Entry_Delta",
    "Explanation",
    "VRF",
    "Protocol",
]


def sanitize_filename_token(raw: str) -> str:
    """Convert an arbitrary identifier into a safe filename token."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw.strip())
    return cleaned.strip("_") or "report"


def _format_metric_display(path: dict[str, Any]) -> str:
    raw = str(path.get("raw_metric") or "").strip()
    if raw:
        return raw
    metric = path.get("metric")
    ad = path.get("admin_distance")
    pp = path.get("peer_priority")
    if metric is None and ad is None:
        return ""
    meta = []
    if ad is not None:
        meta.append(f"AD:{ad}")
    if pp is not None:
        meta.append(f"PP:{pp}")
    return f"{metric} ({', '.join(meta)})" if meta else str(metric)


def _iter_entry_rows(item: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Expand a prefix diff entry into individual (entry_action, path_dict) rows."""
    rows: list[tuple[str, dict[str, Any]]] = []
    for path in item.get("removed_paths") or []:
        rows.append(("REMOVED", path))
    for path in item.get("added_paths") or []:
        rows.append(("ADDED", path))
    if not rows:
        # Fallback if a minimal test payload omitted removed_paths/added_paths
        change_type = str(item.get("change_type") or "").lower()
        if change_type == "removed":
            for path in item.get("before_paths") or []:
                rows.append(("REMOVED", path))
        elif change_type == "added":
            for path in item.get("after_paths") or []:
                rows.append(("ADDED", path))
    return rows


def format_comparison_reports_csv(reports: list[dict[str, Any]]) -> str:
    """Serialize comparison report payloads into row-per-route-entry RFC 4180 CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADERS)

    for report in reports:
        device_label = str(report.get("device_label") or "")
        entries = report.get("all_entries") or []
        for item in entries:
            before_cnt = len(item.get("before_paths") or [])
            after_cnt = len(item.get("after_paths") or [])
            delta = after_cnt - before_cnt
            prefix_change_type = str(item.get("change_type", "")).upper()
            is_important = "YES" if item.get("is_important") else "NO"
            matched_rules = "; ".join(item.get("matched_rules") or [])
            importance_reasons = "; ".join(item.get("importance_reasons") or [])
            explanation = item.get("explanation", "")
            vrf = item.get("vrf", "default")

            for entry_action, path in _iter_entry_rows(item):
                writer.writerow(
                    [
                        device_label,
                        item.get("prefix", ""),
                        path.get("next_hop", ""),
                        path.get("interface", ""),
                        _format_metric_display(path),
                        "" if path.get("admin_distance") is None else path.get("admin_distance"),
                        "" if path.get("metric") is None else path.get("metric"),
                        "" if path.get("peer_priority") is None else path.get("peer_priority"),
                        prefix_change_type,
                        entry_action,
                        is_important,
                        matched_rules,
                        importance_reasons,
                        before_cnt,
                        after_cnt,
                        f"{delta:+d}" if delta != 0 else "0",
                        explanation,
                        vrf,
                        path.get("protocol") or "unknown",
                    ]
                )

    return buf.getvalue()
