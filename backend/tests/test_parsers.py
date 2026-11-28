"""Unit tests for EdgeConnect CSV/JSON, Cisco NX-OS, Cisco IOS-XE, and plain CIDR parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.devices.mock_fixtures import CISCO_NEXUS_BEFORE_CLI, CISCO_ROUTER_BEFORE_CLI
from app.adapters.devices.parsers import (
    auto_parse_routing_text,
    parse_cisco_ios_cli,
    parse_cisco_nxapi_json,
    parse_cisco_nxos_cli,
    parse_edgeconnect_csv,
    parse_edgeconnect_metric,
    parse_edgeconnect_orchestrator_json,
)


def test_parse_edgeconnect_metric_variants():
    assert parse_edgeconnect_metric("50 (AD:15, PP:7)") == (50, 15, 7)
    assert parse_edgeconnect_metric("52 (AD:251)") == (52, 251, None)
    assert parse_edgeconnect_metric("40") == (40, None, None)
    assert parse_edgeconnect_metric("") == (None, None, None)


def test_parse_real_edgeconnect_csv_with_bom(sample_data_dir: Path, using_synthetic_sample_data: bool):
    before_text = (sample_data_dir / "subnetsExample_beforeChange.csv").read_text(encoding="utf-8")
    routes = parse_edgeconnect_csv(before_text)
    assert len(routes) == 4442
    assert routes[0].prefix == "0.0.0.0/0"
    assert routes[0].interface == "lan0"
    assert routes[0].admin_distance == 1
    assert routes[0].metric == 50
    assert routes[0].protocol == "unknown"
    if using_synthetic_sample_data:
        assert routes[0].next_hop == "10.240.0.1"
        assert routes[2].peer_priority == 5
        assert routes[2].protocol == "unknown"
    else:
        assert routes[0].next_hop == "10.162.183.217"
        assert routes[1].peer_priority == 5
        assert routes[1].protocol == "unknown"


def test_parse_edgeconnect_csv_explicit_or_missing_protocol():
    csv_text = (
        "Appliance,Subnet/Mask,Next Hop,Interface,Metric,Protocol\n"
        "ec-01,10.1.0.0/16,10.0.0.1,lan0,50 (AD:20),BGP\n"
        'ec-01,10.2.0.0/16,,,"50 (AD:15, PP:5)",\n'
    )
    routes = parse_edgeconnect_csv(csv_text)
    assert len(routes) == 2
    assert routes[0].protocol == "bgp"
    assert routes[1].protocol == "unknown"


def test_parse_edgeconnect_orchestrator_json():
    payload = {
        "entries": [
            {
                "prefix": "10.127.0.0/16",
                "nexthop": "10.1.1.1",
                "interface": "lan0",
                "metric": 50,
                "ad": 15,
                "peerPriority": 3,
                "segment": "prod",
            },
            {
                "prefix": "10.128.0.0/16",
                "nexthop": "10.1.1.2",
                "interface": "lan0",
                "metric": 20,
                "ad": 20,
                "protocol": "BGP",
            },
        ]
    }
    routes = parse_edgeconnect_orchestrator_json(payload, appliance="ec-01")
    assert len(routes) == 2
    assert routes[0].vrf == "prod"
    assert routes[0].admin_distance == 15
    assert routes[0].peer_priority == 3
    assert routes[0].protocol == "unknown"
    assert routes[1].vrf == "default"
    assert routes[1].protocol == "bgp"


def test_parse_cisco_nxos_cli():
    routes = parse_cisco_nxos_cli(CISCO_NEXUS_BEFORE_CLI, hostname="nx-dc1-core01")
    assert len(routes) == 15
    prefixes = {r.prefix for r in routes}
    assert "0.0.0.0/0" in prefixes
    assert "10.103.0.0/19" in prefixes
    assert "10.126.112.0/20" in prefixes
    bgp_routes = [r for r in routes if r.prefix == "10.127.0.0/16"]
    assert len(bgp_routes) == 2
    assert bgp_routes[0].protocol == "bgp"
    assert bgp_routes[0].admin_distance == 20
    assert {r.metric for r in bgp_routes} == {50, 100}


def test_parse_cisco_nxapi_json():
    payload = {
        "TABLE_vrf": {
            "ROW_vrf": {
                "vrf-name-out": "tenant-a",
                "TABLE_addrf": {
                    "ROW_addrf": {
                        "TABLE_prefix": {
                            "ROW_prefix": {
                                "ipprefix": "10.198.0.0/16",
                                "TABLE_path": {
                                    "ROW_path": {
                                        "ipnexthop": "10.255.30.1",
                                        "ifname": "Eth1/10",
                                        "pref": 20,
                                        "metric": 30,
                                        "clientname": "bgp-65001",
                                    }
                                },
                            }
                        }
                    }
                },
            }
        }
    }
    routes = parse_cisco_nxapi_json(payload, hostname="nx-live")
    assert len(routes) == 1
    assert routes[0].vrf == "tenant-a"
    assert routes[0].prefix == "10.198.0.0/16"
    assert routes[0].protocol == "bgp"


def test_parse_cisco_ios_cli_including_ecmp_continuation():
    routes = parse_cisco_ios_cli(CISCO_ROUTER_BEFORE_CLI, hostname="rtr-hq-wan01")
    assert len(routes) == 11
    multi = [r for r in routes if r.prefix == "10.130.0.0/17"]
    assert len(multi) == 2
    assert {r.metric for r in multi} == {50, 150}
    assert {r.next_hop for r in multi} == {"198.51.100.10", "198.51.100.14"}


def test_auto_parse_plain_cidr_and_invalid_csv():
    routes = auto_parse_routing_text("10.1.0.0/16\n10.1.1.0/24\n# comment\n172.16.2.0/24")
    assert [r.prefix for r in routes] == ["10.1.0.0/16", "10.1.1.0/24", "172.16.2.0/24"]
    assert all(r.protocol == "unknown" for r in routes)

    with pytest.raises(ValueError, match="Unsupported CSV headers"):
        parse_edgeconnect_csv("ColA,ColB\n1,2\n")


def test_synthetic_sample_data_generator_matches_scale_and_pipelines():
    from app.pipelines.comparison.context import ComparisonInput
    from app.pipelines.comparison.pipeline import run_comparison_pipeline
    from app.pipelines.summary.context import SummaryInput
    from app.pipelines.summary.pipeline import run_summary_pipeline
    from scripts.generate_synthetic_sample_data import build_synthetic_csv_pair

    before_csv, after_csv = build_synthetic_csv_pair()
    before_routes = parse_edgeconnect_csv(before_csv)
    after_routes = parse_edgeconnect_csv(after_csv)

    assert len(before_routes) == 4442
    assert len(after_routes) == 4411

    comp = run_comparison_pipeline(
        ComparisonInput(
            device_label="uec-abc-prd01",
            before_routes=[r.to_dict() for r in before_routes],
            after_routes=[r.to_dict() for r in after_routes],
            important_prefixes=["0.0.0.0/0", "10.76.12.0/23", "10.127.0.0/16", "10.130.0.0/17"],
            large_prefix_threshold=20,
        )
    )
    stats = comp["summary_stats"]
    assert stats["before_unique_prefixes"] == 1775
    assert stats["after_unique_prefixes"] == 1766
    assert stats["removed_count"] == 10
    assert stats["added_count"] == 1
    assert stats["changed_count"] == 3
    assert stats["important_count"] == 7
    assert stats["net_entry_delta"] == -31

    summ = run_summary_pipeline(
        SummaryInput(
            source_label="synthetic_after.csv",
            routes=[r.to_dict() for r in after_routes],
        )
    )
    assert summ["total_unique_prefixes"] == 1765
    assert summ["output_route_count"] == 175
    assert summ["summary_route_count"] == 27
    assert summ["remaining_route_count"] == 148
