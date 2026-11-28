"""Comprehensive unit tests for every stage of the Feature 1 Comparison Pipeline."""

from __future__ import annotations

from pathlib import Path

from app.adapters.devices.parsers import parse_edgeconnect_csv
from app.pipelines.comparison.context import ComparisonInput
from app.pipelines.comparison.pipeline import run_comparison_pipeline
from app.services.seed import DEFAULT_IMPORTANT_ROUTES


def test_comparison_pipeline_on_provided_sample_csvs(
    sample_data_dir: Path,
    using_synthetic_sample_data: bool,
):
    before_routes = [
        r.to_dict()
        for r in parse_edgeconnect_csv(
            (sample_data_dir / "subnetsExample_beforeChange.csv").read_text(encoding="utf-8-sig")
        )
    ]
    after_routes = [
        r.to_dict()
        for r in parse_edgeconnect_csv(
            (sample_data_dir / "subnetsExample_afterChange.csv").read_text(encoding="utf-8-sig")
        )
    ]

    result = run_comparison_pipeline(
        ComparisonInput(
            device_label="uec-abc-prd01",
            before_routes=before_routes,
            after_routes=after_routes,
            important_prefixes=[p for p, _ in DEFAULT_IMPORTANT_ROUTES],
            large_prefix_threshold=20,
        )
    )

    stats = result["summary_stats"]
    assert stats["before_raw_entries"] == 4442
    assert stats["after_raw_entries"] == 4411
    assert stats["net_entry_delta"] == -31
    assert stats["before_unique_prefixes"] == 1775
    assert stats["after_unique_prefixes"] == 1766
    assert stats["removed_count"] == 10
    assert stats["added_count"] == 1
    assert stats["changed_count"] == 3
    assert stats["removed_prefix_entries_count"] == 32
    assert stats["added_prefix_entries_count"] == 3
    assert stats["changed_removed_entries_count"] == 8
    assert stats["changed_added_entries_count"] == 6
    assert stats["removed_entries_count"] == 40
    assert stats["added_entries_count"] == 9
    assert stats["total_diff_entry_rows"] == 49
    assert stats["total_differences"] == 14
    assert result["risk_level"] == "CRITICAL"

    important_by_prefix = {e["prefix"]: e for e in result["important_entries"]}
    if using_synthetic_sample_data:
        assert set(important_by_prefix.keys()) == {
            "10.200.0.0/14",
            "10.208.0.0/16",
            "10.212.128.0/17",
            "10.216.16.0/20",
            "0.0.0.0/0",
            "10.127.0.0/16",
            "10.130.0.0/17",
        }
        assert important_by_prefix["10.200.0.0/14"]["fallback_status"] == "no_covering_supernet"
        assert important_by_prefix["10.212.128.0/17"]["fallback_parent_prefix"] == "10.212.0.0/16"
        assert (
            important_by_prefix["10.212.128.0/17"]["fallback_status"]
            == "covering_supernet_egress_unknown"
        )
        assert (
            important_by_prefix["10.216.16.0/20"]["fallback_status"]
            == "covering_supernet_same_next_hop"
        )
    else:
        # Exactly 7 important entries on the original local sample CSVs
        assert set(important_by_prefix.keys()) == {
            "10.121.0.0/16",
            "10.130.128.0/17",
            "10.132.0.0/14",
            "10.76.12.0/23",
            "0.0.0.0/0",
            "10.127.0.0/16",
            "10.130.0.0/17",
        }
        assert important_by_prefix["10.132.0.0/14"]["fallback_status"] == "no_covering_supernet"
        assert important_by_prefix["10.132.0.0/14"]["severity"] == "CRITICAL"

        assert important_by_prefix["10.76.12.0/23"]["fallback_parent_prefix"] == "10.64.0.0/12"
        assert (
            important_by_prefix["10.76.12.0/23"]["fallback_status"]
            == "covering_supernet_egress_unknown"
        )
        assert "cannot be confirmed" in important_by_prefix["10.76.12.0/23"]["explanation"]
        assert "pre_specified_route" in important_by_prefix["10.76.12.0/23"]["matched_rules"]

        assert important_by_prefix["10.127.0.0/16"]["active_path_changed"] is True
        assert important_by_prefix["10.127.0.0/16"]["severity"] == "CRITICAL"
        assert (
            "Lowest recorded (AD, Metric, PP) entry increased"
            in important_by_prefix["10.127.0.0/16"]["explanation"]
        )

        assert important_by_prefix["10.130.0.0/17"]["active_path_changed"] is True
        assert (
            "Recorded route entry count decreased from 4 to 2"
            in important_by_prefix["10.130.0.0/17"]["explanation"]
        )

        default_entry = important_by_prefix["0.0.0.0/0"]
        assert default_entry["active_path_changed"] is False
        assert default_entry["backup_only_changed"] is True
        assert any("twan0" in drift for drift in default_entry["next_hop_changes"])
        assert any("lan0" in drift for drift in default_entry["next_hop_changes"])
        assert "policy-routed" in default_entry["explanation"]

    # Verify pipeline stage telemetry contains all 5 single-responsibility stages
    stage_names = [s["name"] for s in result["pipeline_stages"]]
    assert stage_names == [
        "normalize",
        "diff",
        "importance_classifier",
        "network_analysis",
        "report_assembly",
    ]


def test_prespecified_rule_is_exact_match_only():
    before = [
        {
            "prefix": "10.127.1.0/24",
            "vrf": "default",
            "next_hop": "10.0.0.1",
            "interface": "eth0",
            "admin_distance": 20,
            "metric": 10,
        },
    ]
    after = []
    result = run_comparison_pipeline(
        ComparisonInput(
            device_label="rtr-exact-test",
            before_routes=before,
            after_routes=after,
            important_prefixes=["10.127.0.0/16"],  # parent only — must NOT match /24 child
            large_prefix_threshold=20,
        )
    )
    assert result["summary_stats"]["important_count"] == 0
    assert result["summary_stats"]["normal_count"] == 1


def test_lpm_fallback_detects_egress_mismatch():
    before = [
        {
            "prefix": "10.50.0.0/16",
            "vrf": "default",
            "next_hop": "10.0.0.1",
            "interface": "eth0",
            "admin_distance": 20,
            "metric": 10,
        },
        {
            "prefix": "10.50.10.0/24",
            "vrf": "default",
            "next_hop": "10.0.0.99",
            "interface": "eth9",
            "admin_distance": 20,
            "metric": 10,
        },
    ]
    after = [
        {
            "prefix": "10.50.0.0/16",
            "vrf": "default",
            "next_hop": "10.0.0.1",
            "interface": "eth0",
            "admin_distance": 20,
            "metric": 10,
        },
    ]
    result = run_comparison_pipeline(
        ComparisonInput(
            device_label="rtr-egress-test",
            before_routes=before,
            after_routes=after,
            important_prefixes=[],
        )
    )
    entry = result["normal_entries"][0]
    assert entry["fallback_parent_prefix"] == "10.50.0.0/16"
    assert entry["fallback_status"] == "covering_supernet_different_next_hop"
    assert entry["severity"] == "MEDIUM"


def test_identical_tables_return_pass():
    routes = [
        {
            "prefix": "10.1.0.0/16",
            "vrf": "default",
            "next_hop": "10.0.0.1",
            "interface": "eth0",
            "admin_distance": 20,
            "metric": 10,
        }
    ]
    result = run_comparison_pipeline(
        ComparisonInput(device_label="clean-dev", before_routes=routes, after_routes=routes)
    )
    assert result["risk_level"] == "PASS"
    assert result["summary_stats"]["total_differences"] == 0
