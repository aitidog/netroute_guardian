"""Pluggable network semantic analyzers for Stage 4 of the Comparison Pipeline."""

from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod
from collections import defaultdict

from app.pipelines.comparison.context import ComparisonContext, RouteDiffEntry, RoutePath


class RouteAnalyzer(ABC):
    """Abstract analyzer enriching diff entries with domain-specific networking diagnostics."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique analyzer identifier."""

    @abstractmethod
    def analyze(self, ctx: ComparisonContext) -> None:
        """Inspect and enrich ``ctx.diff_entries`` and context-level metrics."""


def _select_best_tier(paths: list[RoutePath]) -> list[RoutePath]:
    """Return all paths tied for the highest preference (lowest AD, then Metric, then PP)."""
    if not paths:
        return []
    best_key = min(p.preference_key() for p in paths)
    return [p for p in paths if p.preference_key() == best_key]


def _format_path_brief(path: RoutePath) -> str:
    egress_parts = []
    if path.interface:
        egress_parts.append(path.interface)
    if path.next_hop:
        egress_parts.append(f"via {path.next_hop}")
    egress = " ".join(egress_parts) if egress_parts else "SD-WAN overlay"
    metric_label = path.raw_metric or (
        f"Metric:{path.metric} AD:{path.admin_distance}" if path.metric is not None else path.protocol
    )
    return f"{egress} [{metric_label}]"


def _egress_signature(paths: list[RoutePath]) -> set[tuple[str, str]]:
    return {(p.interface, p.next_hop) for p in paths}


class LpmFallbackAnalyzer(RouteAnalyzer):
    """Checks whether removed prefixes still have an active non-default parent route in After.

    Compares the removed route's primary egress against the covering parent's primary egress
    so engineers are warned when traffic falls back to a different next-hop/interface or
    escapes to the default route (0.0.0.0/0).
    """

    @property
    def name(self) -> str:
        return "lpm_fallback_analyzer"

    def analyze(self, ctx: ComparisonContext) -> None:
        # Index non-default after prefixes per VRF sorted from most-specific to least-specific
        # so the first matching supernet is the Longest Prefix Match (LPM).
        after_by_vrf: dict[str, list[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, str]]] = (
            defaultdict(list)
        )
        for vrf, prefix in ctx.after_map:
            net = ipaddress.ip_network(prefix, strict=False)
            if net.prefixlen == 0:
                continue
            after_by_vrf[vrf].append((net, prefix))

        for vrf in after_by_vrf:
            after_by_vrf[vrf].sort(key=lambda item: item[0].prefixlen, reverse=True)

        for entry in ctx.diff_entries:
            if entry.change_type != "removed":
                continue

            removed_net = ipaddress.ip_network(entry.prefix, strict=False)
            if removed_net.prefixlen == 0:
                entry.fallback_status = "default_or_blackhole"
                entry.findings.append(
                    "Default route 0.0.0.0/0 was removed completely; "
                    "external/fallback reachability is broken."
                )
                continue

            lpm_parent_prefix: str | None = None
            for candidate_net, candidate_str in after_by_vrf.get(entry.vrf, []):
                if (
                    candidate_net.version == removed_net.version
                    and candidate_net.prefixlen < removed_net.prefixlen
                    and removed_net.subnet_of(candidate_net)
                ):
                    lpm_parent_prefix = candidate_str
                    break

            if lpm_parent_prefix is None:
                entry.fallback_status = "default_or_blackhole"
                entry.findings.append(
                    "No covering non-default supernet remains in the post-change table; "
                    "traffic will fall back to 0.0.0.0/0 or be blackholed."
                )
            else:
                entry.fallback_parent_prefix = lpm_parent_prefix
                parent_best = _select_best_tier(ctx.after_map[(entry.vrf, lpm_parent_prefix)])
                removed_best = _select_best_tier(entry.before_paths)
                entry.fallback_parent_egress = (
                    _format_path_brief(parent_best[0]) if parent_best else "unknown"
                )

                if _egress_signature(parent_best) == _egress_signature(removed_best):
                    entry.fallback_status = "parent_same_egress"
                    entry.findings.append(
                        f"Specific route removed, but traffic falls back via LPM to active parent "
                        f"{lpm_parent_prefix} ({entry.fallback_parent_egress}) with matching egress."
                    )
                else:
                    entry.fallback_status = "parent_different_egress"
                    entry.findings.append(
                        f"Specific route removed; traffic falls back via LPM to active parent "
                        f"{lpm_parent_prefix} ({entry.fallback_parent_egress}), whose egress differs "
                        f"from the removed route — verify forwarding symmetry and path policy."
                    )


class PathSelectionAnalyzer(RouteAnalyzer):
    """Analyzes primary vs backup path shifts using lexicographic (AD, Metric, PP) preference."""

    @property
    def name(self) -> str:
        return "path_selection_analyzer"

    def analyze(self, ctx: ComparisonContext) -> None:
        for entry in ctx.diff_entries:
            if entry.change_type != "changed":
                continue

            best_before = _select_best_tier(entry.before_paths)
            best_after = _select_best_tier(entry.after_paths)
            entry.best_before_summary = _format_path_brief(best_before[0]) if best_before else "none"
            entry.best_after_summary = _format_path_brief(best_after[0]) if best_after else "none"

            before_best_sigs = {p.signature() for p in best_before}
            after_best_sigs = {p.signature() for p in best_after}
            active_changed = before_best_sigs != after_best_sigs
            entry.active_path_changed = active_changed
            entry.backup_only_changed = not active_changed

            # Detect per-interface next-hop drift among changed paths.
            rem_by_if: dict[str, list[str]] = defaultdict(list)
            add_by_if: dict[str, list[str]] = defaultdict(list)
            for p in entry.removed_paths:
                if p.interface and p.next_hop:
                    rem_by_if[p.interface].append(p.next_hop)
            for p in entry.added_paths:
                if p.interface and p.next_hop:
                    add_by_if[p.interface].append(p.next_hop)

            for iface in sorted(set(rem_by_if) & set(add_by_if)):
                old_nhs = sorted(set(rem_by_if[iface]))
                new_nhs = sorted(set(add_by_if[iface]))
                if old_nhs != new_nhs:
                    drift = f"{iface}: {', '.join(old_nhs)} -> {', '.join(new_nhs)}"
                    entry.next_hop_changes.append(drift)

            if active_changed and best_before and best_after:
                b_key = best_before[0].preference_key()
                a_key = best_after[0].preference_key()
                if a_key > b_key:
                    entry.findings.append(
                        f"Primary path degraded: best route shifted from "
                        f"{entry.best_before_summary} to {entry.best_after_summary} "
                        f"(failover to lower-priority backup path)."
                    )
                elif a_key < b_key:
                    entry.findings.append(
                        f"Primary path preference improved from {entry.best_before_summary} "
                        f"to {entry.best_after_summary} — verify intended traffic engineering."
                    )
                else:
                    entry.findings.append(
                        f"Active forwarding path changed at the same preference tier "
                        f"({entry.best_before_summary} -> {entry.best_after_summary})."
                    )
            else:
                entry.findings.append(
                    f"Highest-priority path ({entry.best_before_summary}) remained unchanged; "
                    f"changes occurred in backup/secondary path tiers."
                )
                if entry.prefix == "0.0.0.0/0":
                    entry.findings.append(
                        "Advisory: on SD-WAN appliances, policy-based routing / Local Breakout "
                        "may actively use secondary WAN/LAN default paths even when AD:1 is unchanged."
                    )

            if entry.next_hop_changes:
                entry.findings.append(
                    "Next-hop drift detected on interface(s): " + "; ".join(entry.next_hop_changes) + "."
                )

            before_cnt = len(entry.before_paths)
            after_cnt = len(entry.after_paths)
            if after_cnt < before_cnt:
                entry.findings.append(f"Path redundancy decreased from {before_cnt} to {after_cnt} path(s).")
            elif after_cnt > before_cnt:
                entry.findings.append(f"Path redundancy increased from {before_cnt} to {after_cnt} path(s).")


class ImpactAssessmentAnalyzer(RouteAnalyzer):
    """Calculates impacted IP address space and assigns per-entry severity and overall risk."""

    _SEVERITY_RANK = {"PASS": 0, "INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}

    @property
    def name(self) -> str:
        return "impact_assessment_analyzer"

    def analyze(self, ctx: ComparisonContext) -> None:
        total_ips_non_default = 0
        highest_rank = 0
        highest_label: str = "PASS"

        for entry in ctx.diff_entries:
            net = ipaddress.ip_network(entry.prefix, strict=False)
            entry.affected_ip_count = int(net.num_addresses)
            if net.prefixlen > 0:
                total_ips_non_default += entry.affected_ip_count

            severity = self._classify_entry_severity(entry)
            entry.severity = severity
            rank = self._SEVERITY_RANK[severity]
            if rank > highest_rank:
                highest_rank = rank
                highest_label = severity

            if entry.change_type == "added":
                entry.findings.append(
                    f"New prefix advertised ({entry.affected_ip_count:,} addresses, "
                    f"{len(entry.after_paths)} path(s))."
                )

        ctx.total_affected_ips_excluding_default = total_ips_non_default
        ctx.overall_risk_level = (
            "PASS" if not ctx.diff_entries else ("LOW" if highest_label == "INFO" else highest_label)
        )  # type: ignore[assignment]

    def _classify_entry_severity(self, entry: RouteDiffEntry) -> str:
        if entry.change_type == "removed":
            if entry.is_important and entry.fallback_status == "default_or_blackhole":
                return "CRITICAL"
            if entry.is_important:
                return "HIGH"
            if entry.fallback_status == "default_or_blackhole":
                return "HIGH"
            if entry.fallback_status == "parent_different_egress":
                return "MEDIUM"
            return "LOW"

        if entry.change_type == "changed":
            if entry.is_important and entry.active_path_changed:
                return "CRITICAL"
            if entry.is_important:
                return "HIGH"
            if entry.active_path_changed:
                return "MEDIUM"
            return "LOW"

        # Added prefix
        if entry.prefix_len <= 20:
            return "MEDIUM"
        return "INFO"
