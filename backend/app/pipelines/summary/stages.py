"""Single-responsibility stages for the Feature 2 Route Summary Pipeline."""

from __future__ import annotations

import ipaddress
from collections import defaultdict

from app.pipelines.base import PipelineStage
from app.pipelines.summary.context import CollapsedRouteNode, SummaryContext


class FilterNormalizeStage(PipelineStage[SummaryContext]):
    """Stage 1: Ignore 0.0.0.0/0 (and ::/0), canonicalize CIDRs, and deduplicate per VRF."""

    @property
    def name(self) -> str:
        return "filter_normalize"

    @property
    def description(self) -> str:
        return "Exclude default routes (0.0.0.0/0), canonicalize CIDRs, and deduplicate per VRF."

    def execute(self, ctx: SummaryContext) -> dict:
        ctx.total_raw_entries = len(ctx.input_data.routes)
        seen_per_vrf: dict[str, set[ipaddress.IPv4Network | ipaddress.IPv6Network]] = defaultdict(set)
        ignored_defaults = 0

        for row in ctx.input_data.routes:
            raw_prefix = str(row.get("prefix") or "").strip()
            if not raw_prefix:
                continue
            net = ipaddress.ip_network(raw_prefix, strict=False)
            if net.prefixlen == 0:
                ignored_defaults += 1
                continue
            vrf = str(row.get("vrf") or "default")
            seen_per_vrf[vrf].add(net)

        ctx.ignored_default_routes = ignored_defaults
        ctx.unique_networks_by_vrf = {vrf: list(nets) for vrf, nets in seen_per_vrf.items()}
        total_unique = sum(len(v) for v in ctx.unique_networks_by_vrf.values())
        return {
            "total_raw_entries": ctx.total_raw_entries,
            "ignored_default_routes": ignored_defaults,
            "unique_non_default_prefixes": total_unique,
            "vrf_count": len(ctx.unique_networks_by_vrf),
        }


class PrefixCollapseStage(PipelineStage[SummaryContext]):
    """Stage 2: Collapse covered more-specific routes via O(N log N) Sorted Monotonic Stack."""

    @property
    def name(self) -> str:
        return "prefix_collapse"

    @property
    def description(self) -> str:
        return "Retain broadest existing covering prefixes and fold covered sub-prefixes via monotonic stack."

    def execute(self, ctx: SummaryContext) -> dict:
        total_kept = 0
        total_covered = 0

        for vrf, networks in sorted(ctx.unique_networks_by_vrf.items()):
            # Separate by IP version so IPv4 and IPv6 never compare across families.
            by_version: dict[int, list[ipaddress.IPv4Network | ipaddress.IPv6Network]] = defaultdict(list)
            for net in networks:
                by_version[net.version].append(net)

            collapsed_nodes: list[CollapsedRouteNode] = []
            for version in sorted(by_version.keys()):
                ordered = sorted(
                    by_version[version],
                    key=lambda n: (int(n.network_address), n.prefixlen),
                )
                # Monotonic stack of active covering (network, top_level_node) pairs.
                stack: list[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, CollapsedRouteNode]] = []
                for net in ordered:
                    while stack and not net.subnet_of(stack[-1][0]):
                        stack.pop()

                    if stack:
                        top_node = stack[0][1]
                        top_node.covered_routes.append(str(net))
                        total_covered += 1
                        stack.append((net, top_node))
                    else:
                        node = CollapsedRouteNode(
                            vrf=vrf,
                            prefix=str(net),
                            prefix_len=net.prefixlen,
                        )
                        collapsed_nodes.append(node)
                        total_kept += 1
                        stack.append((net, node))

            ctx.collapsed_by_vrf[vrf] = collapsed_nodes

        return {
            "retained_output_routes": total_kept,
            "covered_more_specific_routes": total_covered,
        }


class SupernetSuggestionStage(PipelineStage[SummaryContext]):
    """Stage 3 (Optional): Identify adjacent CIDR blocks eligible for synthetic supernetting."""

    @property
    def name(self) -> str:
        return "supernet_suggestions"

    @property
    def description(self) -> str:
        return "Optionally compute adjacent CIDR supernet aggregation suggestions via collapse_addresses."

    def execute(self, ctx: SummaryContext) -> dict:
        if not ctx.input_data.include_supernet_suggestions:
            ctx.supernet_suggestions = None
            return {"enabled": False}

        suggestions: list[dict] = []
        for vrf, nodes in sorted(ctx.collapsed_by_vrf.items()):
            nets_v4 = [
                ipaddress.IPv4Network(n.prefix) for n in nodes if ipaddress.ip_network(n.prefix).version == 4
            ]
            aggregated = list(ipaddress.collapse_addresses(nets_v4))
            existing_set = {str(n) for n in nets_v4}
            for agg in aggregated:
                if str(agg) not in existing_set:
                    members = [str(n) for n in nets_v4 if n.subnet_of(agg)]
                    suggestions.append(
                        {
                            "vrf": vrf,
                            "suggested_supernet": str(agg),
                            "member_count": len(members),
                            "member_prefixes": members,
                        }
                    )
        ctx.supernet_suggestions = suggestions
        return {"enabled": True, "suggestion_count": len(suggestions)}


class SummaryFormatStage(PipelineStage[SummaryContext]):
    """Stage 4: Split output into Summary Routes vs Remaining Routes and compute compression stats."""

    @property
    def name(self) -> str:
        return "summary_format"

    @property
    def description(self) -> str:
        return "Partition retained routes into summary and remaining lists with compression metrics."

    def execute(self, ctx: SummaryContext) -> dict:
        all_nodes = [
            node for vrf in sorted(ctx.collapsed_by_vrf.keys()) for node in ctx.collapsed_by_vrf[vrf]
        ]
        summary_nodes = [n for n in all_nodes if n.is_summary]
        remaining_nodes = [n for n in all_nodes if not n.is_summary]

        total_unique = sum(len(v) for v in ctx.unique_networks_by_vrf.values())
        output_count = len(all_nodes)
        covered_count = total_unique - output_count
        compression_pct = round((covered_count / total_unique) * 100.0, 2) if total_unique > 0 else 0.0

        vrf_groups = [
            {
                "vrf": vrf,
                "unique_prefixes": len(ctx.unique_networks_by_vrf.get(vrf, [])),
                "output_count": len(nodes),
                "summary_count": sum(1 for n in nodes if n.is_summary),
                "remaining_count": sum(1 for n in nodes if not n.is_summary),
            }
            for vrf, nodes in sorted(ctx.collapsed_by_vrf.items())
        ]

        ctx.result_payload = {
            "source_label": ctx.input_data.source_label,
            "device_type": ctx.input_data.device_type,
            "device_ip": ctx.input_data.device_ip,
            "total_raw_entries": ctx.total_raw_entries,
            "total_unique_prefixes": total_unique,
            "ignored_default_routes": ctx.ignored_default_routes,
            "output_route_count": output_count,
            "summary_route_count": len(summary_nodes),
            "remaining_route_count": len(remaining_nodes),
            "covered_route_count": covered_count,
            "compression_ratio_pct": compression_pct,
            "vrf_groups": vrf_groups,
            "summary_routes": [n.to_dict() for n in summary_nodes],
            "remaining_routes": [n.to_dict() for n in remaining_nodes],
            "all_output_routes": [n.to_dict() for n in all_nodes],
            "supernet_suggestions": ctx.supernet_suggestions,
        }
        return {
            "summary_routes": len(summary_nodes),
            "remaining_routes": len(remaining_nodes),
            "compression_ratio_pct": compression_pct,
        }
