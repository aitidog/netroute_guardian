"""Single-responsibility stages composing the Feature 1 Comparison Pipeline."""

from __future__ import annotations

import ipaddress
from collections import Counter, defaultdict

from app.pipelines.base import PipelineStage
from app.pipelines.comparison.analyzers import RouteAnalyzer
from app.pipelines.comparison.context import ComparisonContext, RouteDiffEntry, RoutePath
from app.pipelines.comparison.rules import ImportanceRule


def _group_routes(raw_routes: list[dict]) -> dict[tuple[str, str], list[RoutePath]]:
    grouped: dict[tuple[str, str], list[RoutePath]] = defaultdict(list)
    for item in raw_routes:
        raw_prefix = str(item.get("prefix") or "").strip()
        if not raw_prefix:
            continue
        prefix = str(ipaddress.ip_network(raw_prefix, strict=False))
        vrf = str(item.get("vrf") or "default")
        grouped[(vrf, prefix)].append(
            RoutePath(
                next_hop=str(item.get("next_hop") or ""),
                interface=str(item.get("interface") or ""),
                protocol=str(item.get("protocol") or "unknown"),
                admin_distance=item.get("admin_distance"),
                metric=item.get("metric"),
                peer_priority=item.get("peer_priority"),
                raw_metric=str(item.get("raw_metric") or ""),
            )
        )
    return dict(grouped)


class NormalizeStage(PipelineStage[ComparisonContext]):
    """Stage 1: Canonicalize CIDRs and aggregate multi-path entries by (vrf, prefix)."""

    @property
    def name(self) -> str:
        return "normalize"

    @property
    def description(self) -> str:
        return "Canonicalize CIDR prefixes and group multi-path entries by (VRF, Prefix)."

    def execute(self, ctx: ComparisonContext) -> dict:
        ctx.before_raw_count = len(ctx.input_data.before_routes)
        ctx.after_raw_count = len(ctx.input_data.after_routes)
        ctx.before_map = _group_routes(ctx.input_data.before_routes)
        ctx.after_map = _group_routes(ctx.input_data.after_routes)
        return {
            "before_raw_entries": ctx.before_raw_count,
            "after_raw_entries": ctx.after_raw_count,
            "before_unique_prefixes": len(ctx.before_map),
            "after_unique_prefixes": len(ctx.after_map),
        }


class DiffStage(PipelineStage[ComparisonContext]):
    """Stage 2: Compute pure set/multiset differences (Removed / Added / Changed / Unchanged)."""

    @property
    def name(self) -> str:
        return "diff"

    @property
    def description(self) -> str:
        return "Compute objective Removed, Added, and Changed prefixes with exact path diffs."

    def execute(self, ctx: ComparisonContext) -> dict:
        before_keys = set(ctx.before_map.keys())
        after_keys = set(ctx.after_map.keys())

        removed_keys = before_keys - after_keys
        added_keys = after_keys - before_keys
        common_keys = before_keys & after_keys

        entries: list[RouteDiffEntry] = []
        unchanged = 0

        for vrf, prefix in removed_keys:
            paths = ctx.before_map[(vrf, prefix)]
            net = ipaddress.ip_network(prefix, strict=False)
            entries.append(
                RouteDiffEntry(
                    vrf=vrf,
                    prefix=prefix,
                    prefix_len=net.prefixlen,
                    change_type="removed",
                    before_paths=list(paths),
                    removed_paths=list(paths),
                )
            )

        for vrf, prefix in added_keys:
            paths = ctx.after_map[(vrf, prefix)]
            net = ipaddress.ip_network(prefix, strict=False)
            entries.append(
                RouteDiffEntry(
                    vrf=vrf,
                    prefix=prefix,
                    prefix_len=net.prefixlen,
                    change_type="added",
                    after_paths=list(paths),
                    added_paths=list(paths),
                )
            )

        for vrf, prefix in common_keys:
            b_paths = ctx.before_map[(vrf, prefix)]
            a_paths = ctx.after_map[(vrf, prefix)]
            b_counter = Counter(p.signature() for p in b_paths)
            a_counter = Counter(p.signature() for p in a_paths)

            if b_counter == a_counter:
                unchanged += 1
                continue

            sig_to_path: dict[tuple, RoutePath] = {}
            for p in b_paths + a_paths:
                sig_to_path.setdefault(p.signature(), p)

            rem_diff = b_counter - a_counter
            add_diff = a_counter - b_counter
            common_cnt = sum((b_counter & a_counter).values())

            removed_list = [sig_to_path[sig] for sig, cnt in rem_diff.items() for _ in range(cnt)]
            added_list = [sig_to_path[sig] for sig, cnt in add_diff.items() for _ in range(cnt)]
            net = ipaddress.ip_network(prefix, strict=False)

            entries.append(
                RouteDiffEntry(
                    vrf=vrf,
                    prefix=prefix,
                    prefix_len=net.prefixlen,
                    change_type="changed",
                    before_paths=list(b_paths),
                    after_paths=list(a_paths),
                    removed_paths=removed_list,
                    added_paths=added_list,
                    unchanged_path_count=common_cnt,
                )
            )

        # Stable deterministic ordering by (vrf, IP integer, prefix_len)
        entries.sort(
            key=lambda e: (
                e.vrf,
                int(ipaddress.ip_network(e.prefix, strict=False).network_address),
                e.prefix_len,
            )
        )
        ctx.diff_entries = entries
        ctx.unchanged_prefix_count = unchanged

        return {
            "removed": len(removed_keys),
            "added": len(added_keys),
            "changed": len(entries) - len(removed_keys) - len(added_keys),
            "unchanged": unchanged,
        }


class ImportanceClassifierStage(PipelineStage[ComparisonContext]):
    """Stage 3: Apply pluggable ImportanceRule objects (e.g. mask <= /20, pre-specified routes)."""

    def __init__(self, rules: list[ImportanceRule]) -> None:
        self._rules = list(rules)

    @property
    def name(self) -> str:
        return "importance_classifier"

    @property
    def description(self) -> str:
        return "Evaluate mask-length and pre-specified critical route rules to highlight high-priority items."

    def execute(self, ctx: ComparisonContext) -> dict:
        important_count = 0
        rule_hits: Counter[str] = Counter()

        for entry in ctx.diff_entries:
            for rule in self._rules:
                match = rule.evaluate(entry)
                if match is not None:
                    entry.is_important = True
                    entry.matched_rules.append(match.rule_id)
                    entry.importance_reasons.append(match.reason)
                    rule_hits[match.rule_id] += 1
            if entry.is_important:
                important_count += 1

        return {
            "important_entries": important_count,
            "normal_entries": len(ctx.diff_entries) - important_count,
            "rule_hits": dict(rule_hits),
        }


class NetworkAnalysisStage(PipelineStage[ComparisonContext]):
    """Stage 4: Execute pluggable networking analyzers (LPM fallback, AD/Metric selection, impact)."""

    def __init__(self, analyzers: list[RouteAnalyzer]) -> None:
        self._analyzers = list(analyzers)

    @property
    def name(self) -> str:
        return "network_analysis"

    @property
    def description(self) -> str:
        return (
            "Run LPM fallback detection, AD/Metric primary-backup analysis, and impact severity assessment."
        )

    def execute(self, ctx: ComparisonContext) -> dict:
        for analyzer in self._analyzers:
            analyzer.analyze(ctx)
        return {
            "analyzers_executed": [a.name for a in self._analyzers],
            "overall_risk_level": ctx.overall_risk_level,
            "affected_ips_excluding_default": ctx.total_affected_ips_excluding_default,
        }


class ReportAssemblyStage(PipelineStage[ComparisonContext]):
    """Stage 5: Assemble the structured comparison report and human-readable explanations."""

    _SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

    @property
    def name(self) -> str:
        return "report_assembly"

    @property
    def description(self) -> str:
        return "Build executive summary, prioritized important/normal sections, and explanations."

    def execute(self, ctx: ComparisonContext) -> dict:
        for entry in ctx.diff_entries:
            parts: list[str] = []
            if entry.importance_reasons:
                parts.append("Priority trigger: " + "; ".join(entry.importance_reasons) + ".")
            parts.extend(entry.findings)
            entry.explanation = " ".join(parts) if parts else "Route state changed."

        # Sort important entries by severity first, then prefix
        important_entries = sorted(
            [e for e in ctx.diff_entries if e.is_important],
            key=lambda e: (
                self._SEVERITY_ORDER.get(e.severity, 9),
                e.change_type != "removed",
                e.prefix_len,
                int(ipaddress.ip_network(e.prefix, strict=False).network_address),
            ),
        )
        normal_entries = sorted(
            [e for e in ctx.diff_entries if not e.is_important],
            key=lambda e: (
                self._SEVERITY_ORDER.get(e.severity, 9),
                e.change_type,
                int(ipaddress.ip_network(e.prefix, strict=False).network_address),
            ),
        )

        removed_count = sum(1 for e in ctx.diff_entries if e.change_type == "removed")
        added_count = sum(1 for e in ctx.diff_entries if e.change_type == "added")
        changed_count = sum(1 for e in ctx.diff_entries if e.change_type == "changed")
        removed_prefix_entries_count = sum(
            len(e.removed_paths) for e in ctx.diff_entries if e.change_type == "removed"
        )
        added_prefix_entries_count = sum(
            len(e.added_paths) for e in ctx.diff_entries if e.change_type == "added"
        )
        changed_removed_entries_count = sum(
            len(e.removed_paths) for e in ctx.diff_entries if e.change_type == "changed"
        )
        changed_added_entries_count = sum(
            len(e.added_paths) for e in ctx.diff_entries if e.change_type == "changed"
        )
        removed_entries_count = removed_prefix_entries_count + changed_removed_entries_count
        added_entries_count = added_prefix_entries_count + changed_added_entries_count
        large_prefix_hits = sum(1 for e in important_entries if "large_prefix" in e.matched_rules)
        prespecified_hits = sum(1 for e in important_entries if "pre_specified_route" in e.matched_rules)

        summary_stats = {
            "device_label": ctx.input_data.device_label,
            "before_raw_entries": ctx.before_raw_count,
            "after_raw_entries": ctx.after_raw_count,
            "net_entry_delta": ctx.after_raw_count - ctx.before_raw_count,
            "before_unique_prefixes": len(ctx.before_map),
            "after_unique_prefixes": len(ctx.after_map),
            "removed_count": removed_count,
            "added_count": added_count,
            "changed_count": changed_count,
            "removed_entries_count": removed_entries_count,
            "added_entries_count": added_entries_count,
            "removed_prefix_entries_count": removed_prefix_entries_count,
            "added_prefix_entries_count": added_prefix_entries_count,
            "changed_removed_entries_count": changed_removed_entries_count,
            "changed_added_entries_count": changed_added_entries_count,
            "total_diff_entry_rows": removed_entries_count + added_entries_count,
            "unchanged_count": ctx.unchanged_prefix_count,
            "total_differences": len(ctx.diff_entries),
            "important_count": len(important_entries),
            "normal_count": len(normal_entries),
            "large_prefix_alert_count": large_prefix_hits,
            "prespecified_alert_count": prespecified_hits,
            "large_prefix_threshold": ctx.input_data.large_prefix_threshold,
            "affected_ips_excluding_default": ctx.total_affected_ips_excluding_default,
            "risk_level": ctx.overall_risk_level,
        }

        executive_summary = self._build_executive_summary(summary_stats)

        ctx.report_payload = {
            "device_label": ctx.input_data.device_label,
            "risk_level": ctx.overall_risk_level,
            "executive_summary": executive_summary,
            "summary_stats": summary_stats,
            "important_entries": [e.to_dict() for e in important_entries],
            "normal_entries": [e.to_dict() for e in normal_entries],
            "all_entries": [e.to_dict() for e in important_entries + normal_entries],
        }
        return {
            "important_section_count": len(important_entries),
            "normal_section_count": len(normal_entries),
        }

    def _build_executive_summary(self, stats: dict) -> str:
        if stats["total_differences"] == 0:
            return (
                f"No routing table differences detected on {stats['device_label']} "
                f"({stats['after_unique_prefixes']} unique prefixes verified)."
            )
        return (
            f"Detected {stats['total_differences']} prefix difference(s) on {stats['device_label']}: "
            f"{stats['removed_count']} removed (-{stats['removed_prefix_entries_count']} entries), "
            f"{stats['added_count']} added (+{stats['added_prefix_entries_count']} entries), "
            f"{stats['changed_count']} changed "
            f"(-{stats['changed_removed_entries_count']}/+{stats['changed_added_entries_count']} entries). "
            f"Total route entries: {stats['before_raw_entries']} -> {stats['after_raw_entries']} "
            f"({stats['net_entry_delta']:+d}). "
            f"{stats['important_count']} high-priority prefix(es) flagged "
            f"({stats['large_prefix_alert_count']} mask <= /{stats['large_prefix_threshold']}, "
            f"{stats['prespecified_alert_count']} pre-specified critical route(s)). "
            f"Overall risk assessment: {stats['risk_level']}."
        )
