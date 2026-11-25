"""Pluggable network semantic analyzers for Stage 4 of the Comparison Pipeline.

Design principle (Evidence-Based Reporting):
Analyzers report strictly what is observable in the collected routing table snapshots
(covering supernet presence, recorded Next Hop / Interface changes, recorded AD / Metric / PP
deltas, entry counts, and IP address scope) without speculating on live device FIB/PBR
forwarding behavior when transport exports omit active-route or tunnel metadata.
"""

from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod
from collections import defaultdict

from app.pipelines.comparison.context import ComparisonContext, RouteDiffEntry, RoutePath


class RouteAnalyzer(ABC):
    """Abstract analyzer enriching diff entries with objective networking observations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique analyzer identifier."""

    @abstractmethod
    def analyze(self, ctx: ComparisonContext) -> None:
        """Inspect and enrich ``ctx.diff_entries`` and context-level metrics."""


def _select_lowest_preference_tier(paths: list[RoutePath]) -> list[RoutePath]:
    """Return all recorded paths tied for the lowest (AD, Metric, PP) tuple."""
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
    egress = " ".join(egress_parts) if egress_parts else "unspecified next-hop/interface"
    metric_label = path.raw_metric or (
        f"Metric:{path.metric} AD:{path.admin_distance}" if path.metric is not None else path.protocol
    )
    return f"{egress} [{metric_label}]"


def _has_explicit_egress(paths: list[RoutePath]) -> bool:
    """Return True only when at least one path records an explicit next-hop or interface."""
    return any(bool(p.interface or p.next_hop) for p in paths)


def _egress_signature(paths: list[RoutePath]) -> set[tuple[str, str]]:
    return {(p.interface, p.next_hop) for p in paths if p.interface or p.next_hop}


class LpmFallbackAnalyzer(RouteAnalyzer):
    """Checks whether a broader non-default prefix exists in the post-change table.

    Reports strictly observable covering-prefix presence and recorded next-hop/interface
    comparison. When Next Hop and Interface are blank (e.g. SD-WAN CSV exports without
    tunnel metadata), explicitly marks egress as unverifiable rather than assuming a match.
    """

    @property
    def name(self) -> str:
        return "lpm_fallback_analyzer"

    def analyze(self, ctx: ComparisonContext) -> None:
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
                entry.fallback_status = "no_covering_supernet"
                entry.findings.append(
                    "Default route 0.0.0.0/0 is absent from the post-change table; "
                    "verify default reachability on the device."
                )
                continue

            covering_parent_prefix: str | None = None
            for candidate_net, candidate_str in after_by_vrf.get(entry.vrf, []):
                if (
                    candidate_net.version == removed_net.version
                    and candidate_net.prefixlen < removed_net.prefixlen
                    and removed_net.subnet_of(candidate_net)
                ):
                    covering_parent_prefix = candidate_str
                    break

            if covering_parent_prefix is None:
                entry.fallback_status = "no_covering_supernet"
                entry.findings.append(
                    "No broader non-default covering prefix exists in the post-change table "
                    "(only 0.0.0.0/0 may match, if present). Verify active forwarding on the device."
                )
                continue

            entry.fallback_parent_prefix = covering_parent_prefix
            parent_tier = _select_lowest_preference_tier(ctx.after_map[(entry.vrf, covering_parent_prefix)])
            removed_tier = _select_lowest_preference_tier(entry.before_paths)
            entry.fallback_parent_egress = (
                _format_path_brief(parent_tier[0]) if parent_tier else "unspecified"
            )

            if not _has_explicit_egress(removed_tier) or not _has_explicit_egress(parent_tier):
                entry.fallback_status = "covering_supernet_egress_unknown"
                entry.findings.append(
                    f"Broader prefix {covering_parent_prefix} exists in the post-change table, "
                    "but Next Hop / Interface fields are blank in this export; actual traffic "
                    "takeover and egress cannot be confirmed without checking live device RIB/FIB "
                    "and routing policy."
                )
            elif _egress_signature(parent_tier) == _egress_signature(removed_tier):
                entry.fallback_status = "covering_supernet_same_next_hop"
                entry.findings.append(
                    f"Broader prefix {covering_parent_prefix} exists in the post-change table "
                    f"with the same recorded Next Hop/Interface ({entry.fallback_parent_egress}); "
                    "verify active forwarding and routing policy on the device."
                )
            else:
                entry.fallback_status = "covering_supernet_different_next_hop"
                entry.findings.append(
                    f"Broader prefix {covering_parent_prefix} exists in the post-change table "
                    f"with a different recorded Next Hop/Interface ({entry.fallback_parent_egress}); "
                    "verify forwarding path and routing policy on the device."
                )


class PathSelectionAnalyzer(RouteAnalyzer):
    """Summarizes recorded AD / Metric / PP shifts, next-hop deltas, and entry count changes.

    Avoids asserting live forwarding failover when device-specific route selection policies
    or active FIB flags are not present in the snapshot.
    """

    @property
    def name(self) -> str:
        return "path_selection_analyzer"

    def analyze(self, ctx: ComparisonContext) -> None:
        for entry in ctx.diff_entries:
            if entry.change_type != "changed":
                continue

            lowest_before = _select_lowest_preference_tier(entry.before_paths)
            lowest_after = _select_lowest_preference_tier(entry.after_paths)
            entry.best_before_summary = _format_path_brief(lowest_before[0]) if lowest_before else "none"
            entry.best_after_summary = _format_path_brief(lowest_after[0]) if lowest_after else "none"

            before_sigs = {p.signature() for p in lowest_before}
            after_sigs = {p.signature() for p in lowest_after}
            lowest_tier_changed = before_sigs != after_sigs
            entry.active_path_changed = lowest_tier_changed
            entry.backup_only_changed = not lowest_tier_changed

            # Detect per-interface recorded next-hop changes.
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

            if lowest_tier_changed and lowest_before and lowest_after:
                b_key = lowest_before[0].preference_key()
                a_key = lowest_after[0].preference_key()
                if a_key > b_key:
                    entry.findings.append(
                        f"Lowest recorded (AD, Metric, PP) entry increased from "
                        f"{entry.best_before_summary} to {entry.best_after_summary} "
                        f"(-{len(entry.removed_paths)} / +{len(entry.added_paths)} entries). "
                        "Verify active route selection on the device."
                    )
                elif a_key < b_key:
                    entry.findings.append(
                        f"Lowest recorded (AD, Metric, PP) entry decreased from "
                        f"{entry.best_before_summary} to {entry.best_after_summary} "
                        f"(-{len(entry.removed_paths)} / +{len(entry.added_paths)} entries). "
                        "Verify active route selection on the device."
                    )
                else:
                    entry.findings.append(
                        f"Recorded entry changed at the lowest (AD, Metric, PP) tier "
                        f"({entry.best_before_summary} -> {entry.best_after_summary}). "
                        "Verify active forwarding on the device."
                    )
            else:
                entry.findings.append(
                    f"Lowest recorded (AD, Metric, PP) entry ({entry.best_before_summary}) "
                    f"is unchanged; {len(entry.removed_paths)} other entry/entries removed and "
                    f"{len(entry.added_paths)} added. Verify device routing policy if secondary "
                    "or policy-routed paths are in use."
                )

            if entry.next_hop_changes:
                entry.findings.append(
                    "Recorded Next Hop changed on interface(s): " + "; ".join(entry.next_hop_changes) + "."
                )

            before_cnt = len(entry.before_paths)
            after_cnt = len(entry.after_paths)
            if after_cnt != before_cnt:
                direction = "decreased" if after_cnt < before_cnt else "increased"
                entry.findings.append(
                    f"Recorded route entry count {direction} from {before_cnt} to {after_cnt}."
                )


class ImpactAssessmentAnalyzer(RouteAnalyzer):
    """Calculates IP address scope and assigns evidence-based severity and overall risk."""

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
                    f"New prefix observed ({entry.affected_ip_count:,} addresses, "
                    f"{len(entry.after_paths)} route entry/entries)."
                )

        ctx.total_affected_ips_excluding_default = total_ips_non_default
        ctx.overall_risk_level = (
            "PASS" if not ctx.diff_entries else ("LOW" if highest_label == "INFO" else highest_label)
        )  # type: ignore[assignment]

    def _classify_entry_severity(self, entry: RouteDiffEntry) -> str:
        if entry.change_type == "removed":
            if entry.is_important and entry.fallback_status == "no_covering_supernet":
                return "CRITICAL"
            if entry.is_important:
                return "HIGH"
            if entry.fallback_status == "no_covering_supernet":
                return "HIGH"
            if entry.fallback_status == "covering_supernet_different_next_hop":
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
