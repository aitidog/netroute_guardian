"""Comprehensive unit tests for the Feature 2 Route Summary Pipeline."""

from __future__ import annotations

from pathlib import Path

from app.adapters.devices.parsers import parse_edgeconnect_csv
from app.pipelines.summary.context import SummaryInput
from app.pipelines.summary.pipeline import run_summary_pipeline


def test_route_summary_matches_requirement_mini_example():
    input_prefixes = [
        "0.0.0.0/0",  # must be ignored
        "10.1.0.0/16",
        "10.1.1.0/24",
        "10.1.5.0/25",
        "10.2.2.0/26",
        "172.16.2.0/24",
        "172.16.2.128/26",
        "192.168.8.0/26",
    ]
    result = run_summary_pipeline(
        SummaryInput(
            source_label="Requirement Mini Example",
            routes=[{"prefix": p, "vrf": "default"} for p in input_prefixes],
        )
    )

    assert result["ignored_default_routes"] == 1
    assert result["total_unique_prefixes"] == 7
    assert [r["prefix"] for r in result["all_output_routes"]] == [
        "10.1.0.0/16",
        "10.2.2.0/26",
        "172.16.2.0/24",
        "192.168.8.0/26",
    ]
    assert [r["prefix"] for r in result["summary_routes"]] == [
        "10.1.0.0/16",
        "172.16.2.0/24",
    ]
    assert [r["prefix"] for r in result["remaining_routes"]] == [
        "10.2.2.0/26",
        "192.168.8.0/26",
    ]
    covered_map = {r["prefix"]: r["covered_routes"] for r in result["summary_routes"]}
    assert covered_map["10.1.0.0/16"] == ["10.1.1.0/24", "10.1.5.0/25"]
    assert covered_map["172.16.2.0/24"] == ["172.16.2.128/26"]


def test_route_summary_on_provided_after_change_csv(
    sample_data_dir: Path,
    using_synthetic_sample_data: bool,
):
    routes = [
        r.to_dict()
        for r in parse_edgeconnect_csv(
            (sample_data_dir / "subnetsExample_afterChange.csv").read_text(encoding="utf-8-sig")
        )
    ]
    result = run_summary_pipeline(
        SummaryInput(
            source_label="subnetsExample_afterChange.csv",
            routes=routes,
            include_supernet_suggestions=True,
        )
    )

    assert result["total_raw_entries"] == 4411
    assert result["ignored_default_routes"] == (14 if using_synthetic_sample_data else 15)
    assert result["total_unique_prefixes"] == 1765
    assert result["output_route_count"] == 175
    assert result["summary_route_count"] == 27
    assert result["remaining_route_count"] == 148
    assert result["covered_route_count"] == 1590
    assert result["compression_ratio_pct"] > 90.0
    assert result["supernet_suggestions"] is not None

    summary_map = {r["prefix"]: r for r in result["summary_routes"]}
    if using_synthetic_sample_data:
        assert "10.212.0.0/16" in summary_map
        assert summary_map["10.212.0.0/16"]["covered_count"] == 59
    else:
        # Verify nested containment on original local sample CSVs
        assert "10.48.0.0/13" in summary_map
        assert "10.51.0.0/16" in summary_map["10.48.0.0/13"]["covered_routes"]
        assert "10.54.0.0/16" in summary_map["10.48.0.0/13"]["covered_routes"]
        assert "10.156.0.0/16" in summary_map
        assert summary_map["10.156.0.0/16"]["covered_count"] == 304


def test_route_summary_isolates_vrfs_and_handles_supernet_suggestions():
    routes = [
        {"prefix": "10.10.0.0/24", "vrf": "vrf-a"},
        {"prefix": "10.10.1.0/24", "vrf": "vrf-a"},
        {"prefix": "10.10.0.0/16", "vrf": "vrf-b"},
    ]
    result = run_summary_pipeline(
        SummaryInput(
            source_label="multi-vrf",
            routes=routes,
            include_supernet_suggestions=True,
        )
    )
    # vrf-b's /16 must NOT collapse vrf-a's /24s
    assert result["output_route_count"] == 3
    assert len(result["vrf_groups"]) == 2
    assert any(
        s["vrf"] == "vrf-a" and s["suggested_supernet"] == "10.10.0.0/23"
        for s in result["supernet_suggestions"]
    )
