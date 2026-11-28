"""Deterministic generator for synthetic, non-proprietary EdgeConnect sample CSVs.

Produces structurally equivalent, equal-volume before/after routing table CSVs
(4,442 before rows / 1,775 unique prefixes; 4,411 after rows / 1,766 unique prefixes)
entirely within synthetic RFC 1918 address space so public demo deployments never
expose confidential or third-party sample routing tables.

Usage:
    uv run python scripts/generate_synthetic_sample_data.py --output-dir ../deploy/sample_data
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

CSV_HEADERS = ["Appliance", "Subnet/Mask", "Next Hop", "Interface", "Metric"]
DEFAULT_APPLIANCE = "uec-abc-prd01"

# Synthetic 27 /16 supernets (disjoint RFC 1918 ranges) for Feature 2 summarization (~90.1% collapse)
SUMMARY_SUPERNETS: list[str] = [
    "10.212.0.0/16",
    "10.216.0.0/16",
    *[f"10.{octet}.0.0/16" for octet in range(180, 195)],  # 15 blocks
    *[f"172.{octet}.0.0/16" for octet in range(20, 30)],  # 10 blocks
]

OVERLAY_METRICS: list[str] = [
    "50 (AD:15, PP:5)",
    "50 (AD:15, PP:7)",
    "60 (AD:15, PP:7)",
    "70 (AD:15, PP:9)",
    "52 (AD:251)",
]


def _make_rows(
    appliance: str,
    prefix: str,
    count: int,
    *,
    lan_next_hop: str = "",
    lan_interface: str = "",
    metric_offset: int = 0,
) -> list[list[str]]:
    rows: list[list[str]] = []
    for idx in range(count):
        if idx == 0 and lan_next_hop:
            metric = f"{50 + (metric_offset % 10)} (AD:1)"
            rows.append([appliance, prefix, lan_next_hop, lan_interface or "lan0", metric])
        else:
            metric = OVERLAY_METRICS[(idx + metric_offset) % len(OVERLAY_METRICS)]
            rows.append([appliance, prefix, "", "", metric])
    return rows


def build_synthetic_csv_pair(appliance: str = DEFAULT_APPLIANCE) -> tuple[str, str]:
    """Generate deterministic synthetic (before_csv, after_csv) strings with UTF-8 BOM."""
    before_rows: list[list[str]] = []
    after_rows: list[list[str]] = []

    # 1. Default route 0.0.0.0/0 (changed: 15 -> 14 entries; -2 / +1, primary lan0 next-hop shift)
    before_default = [
        [appliance, "0.0.0.0/0", "10.240.0.1", "lan0", "50 (AD:1)"],
        [appliance, "0.0.0.0/0", "10.240.0.2", "lan0", "55 (AD:1)"],
        *[
            [appliance, "0.0.0.0/0", "", "", f"{50 + i * 5} (AD:15, PP:{5 + (i % 5)})"]
            for i in range(12)
        ],
        [appliance, "0.0.0.0/0", "", "", "52 (AD:251)"],
    ]
    after_default = [
        [appliance, "0.0.0.0/0", "10.240.0.254", "lan0", "50 (AD:1)"],  # next-hop changed
        [appliance, "0.0.0.0/0", "10.240.0.2", "lan0", "55 (AD:1)"],
        *[
            [appliance, "0.0.0.0/0", "", "", f"{50 + i * 5} (AD:15, PP:{5 + (i % 5)})"]
            for i in range(11)  # 1 overlay entry removed
        ],
        [appliance, "0.0.0.0/0", "", "", "52 (AD:251)"],
    ]
    before_rows.extend(before_default)
    after_rows.extend(after_default)

    # 2. Pre-specified critical routes (from public requirement prompt examples)
    # 2a. 10.76.12.0/23 unchanged (3 entries)
    unchanged_crit = _make_rows(appliance, "10.76.12.0/23", 3, lan_next_hop="10.240.1.1", metric_offset=1)
    before_rows.extend(unchanged_crit)
    after_rows.extend(unchanged_crit)

    # 2b. 10.127.0.0/16 changed (-3 / +2 entries; net -1, lan0 next-hop shift)
    before_127 = [
        [appliance, "10.127.0.0/16", "10.240.10.1", "lan0", "50 (AD:1)"],
        [appliance, "10.127.0.0/16", "", "", "50 (AD:15, PP:5)"],
        [appliance, "10.127.0.0/16", "", "", "60 (AD:15, PP:7)"],
        [appliance, "10.127.0.0/16", "", "", "75 (AD:15, PP:9)"],
        [appliance, "10.127.0.0/16", "", "", "52 (AD:251)"],
    ]
    after_127 = [
        [appliance, "10.127.0.0/16", "10.240.10.2", "lan0", "50 (AD:1)"],  # shifted
        [appliance, "10.127.0.0/16", "", "", "50 (AD:15, PP:5)"],  # unchanged
        [appliance, "10.127.0.0/16", "", "", "65 (AD:15, PP:6)"],  # added
        [appliance, "10.127.0.0/16", "", "", "52 (AD:251)"],  # unchanged
    ]
    before_rows.extend(before_127)
    after_rows.extend(after_127)

    # 2c. 10.130.0.0/17 changed (-3 / +3 entries; net 0, metric/PP shift)
    before_130 = [
        [appliance, "10.130.0.0/17", "", "", "50 (AD:15, PP:5)"],
        [appliance, "10.130.0.0/17", "", "", "55 (AD:15, PP:6)"],
        [appliance, "10.130.0.0/17", "", "", "65 (AD:15, PP:7)"],
        [appliance, "10.130.0.0/17", "", "", "80 (AD:15, PP:9)"],
        [appliance, "10.130.0.0/17", "", "", "52 (AD:251)"],
    ]
    after_130 = [
        [appliance, "10.130.0.0/17", "", "", "50 (AD:15, PP:5)"],  # unchanged
        [appliance, "10.130.0.0/17", "", "", "58 (AD:15, PP:6)"],  # changed
        [appliance, "10.130.0.0/17", "", "", "68 (AD:15, PP:7)"],  # changed
        [appliance, "10.130.0.0/17", "", "", "85 (AD:15, PP:9)"],  # changed
        [appliance, "10.130.0.0/17", "", "", "52 (AD:251)"],  # unchanged
    ]
    before_rows.extend(before_130)
    after_rows.extend(after_130)

    # 3. Four removed broad subnets (mask <= /20 -> IMPORTANT, 14 entries removed)
    removed_important = [
        # No covering supernet in after-table
        ("10.200.0.0/14", 4, "", ""),
        ("10.208.0.0/16", 4, "", ""),
        # Covered by 10.212.0.0/16 (blank egress -> covering_supernet_egress_unknown)
        ("10.212.128.0/17", 3, "", ""),
        # Covered by 10.216.0.0/16 (explicit lan0 next-hop -> covering_supernet_same_next_hop)
        ("10.216.16.0/20", 3, "10.240.20.1", "lan0"),
    ]
    for idx, (pfx, cnt, nh, iface) in enumerate(removed_important):
        before_rows.extend(
            _make_rows(
                appliance,
                pfx,
                cnt,
                lan_next_hop=nh,
                lan_interface=iface,
                metric_offset=idx,
            )
        )

    # 4. Six removed normal subnets (mask > /20, 18 entries removed)
    removed_normal = [
        ("10.224.1.0/24", 3),
        ("10.224.2.0/24", 3),
        ("10.224.3.0/25", 3),
        ("10.224.4.0/25", 3),
        ("10.224.5.0/26", 3),
        ("10.224.6.0/26", 3),
    ]
    for idx, (pfx, cnt) in enumerate(removed_normal):
        before_rows.extend(_make_rows(appliance, pfx, cnt, metric_offset=idx + 2))

    # 5. One added normal subnet (3 entries added)
    after_rows.extend(_make_rows(appliance, "10.232.44.128/25", 3, metric_offset=1))

    # 6. Build 27 summary /16 supernets + 1,590 covered child subnets + 144 standalone subnets
    #    All identical in both Before and After -> exact 1,765 non-default prefixes in After!
    stable_prefixes: list[tuple[str, str, str]] = []
    for supernet in SUMMARY_SUPERNETS:
        if supernet == "10.216.0.0/16":
            stable_prefixes.append((supernet, "10.240.20.1", "lan0"))
        else:
            stable_prefixes.append((supernet, "", ""))

    covered_needed = 1590
    covered_added = 0
    for s_idx, supernet in enumerate(SUMMARY_SUPERNETS):
        base_parts = supernet.split("/")[0].split(".")
        first, second = int(base_parts[0]), int(base_parts[1])
        # Avoid colliding with removed 10.212.128.0/17 or 10.216.16.0/20
        per_block = 59 if s_idx < 26 else (covered_needed - covered_added)
        for c_idx in range(per_block):
            third = 40 + c_idx  # 40..98 stays strictly clear of 16..31 and 128..255
            mask = 24 if c_idx % 2 == 0 else 25
            stable_prefixes.append((f"{first}.{second}.{third}.0/{mask}", "", ""))
            covered_added += 1

    assert covered_added == 1590

    # 144 standalone unsummarizable subnets across 10.236.x.x..10.238.x.x & 192.168.x.x
    for idx in range(144):
        if idx < 100:
            stable_prefixes.append((f"10.236.{idx}.0/24", "", ""))
        else:
            sub = idx - 100
            stable_prefixes.append((f"192.168.{10 + sub}.0/25", "", ""))

    # Target exact total rows: 4,442 Before / 4,411 After
    # Currently before_rows has: 15 + 3 + 5 + 5 + 14 + 18 = 60 rows
    # Currently after_rows has:  14 + 3 + 4 + 5 + 3       = 29 rows
    # Remaining stable entries needed = 4,442 - 60 = 4,382 rows across 1,761 stable prefixes!
    # 1,761 * 2 = 3,522 -> we add +1 entry to 860 prefixes (so 860 have 3 entries, 901 have 2 entries)
    # 860 * 3 + 901 * 2 = 2,580 + 1,802 = 4,382 exact!
    assert len(stable_prefixes) == 27 + 1590 + 144 == 1761
    extra_entries = (4442 - len(before_rows)) - (len(stable_prefixes) * 2)
    assert 0 <= extra_entries <= len(stable_prefixes)

    for idx, (pfx, nh, iface) in enumerate(stable_prefixes):
        entry_cnt = 3 if idx < extra_entries else 2
        rows = _make_rows(appliance, pfx, entry_cnt, lan_next_hop=nh, lan_interface=iface, metric_offset=idx)
        before_rows.extend(rows)
        after_rows.extend(rows)

    assert len(before_rows) == 4442
    assert len(after_rows) == 4411

    return _encode_csv(before_rows), _encode_csv(after_rows)


def _encode_csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    writer.writerows(rows)
    return "\ufeff" + buf.getvalue()


def write_synthetic_sample_data(output_dir: Path, appliance: str = DEFAULT_APPLIANCE) -> tuple[Path, Path]:
    """Write synthetic before/after EdgeConnect CSV files to ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    before_csv, after_csv = build_synthetic_csv_pair(appliance=appliance)
    before_path = output_dir / "subnetsExample_beforeChange.csv"
    after_path = output_dir / "subnetsExample_afterChange.csv"
    before_path.write_text(before_csv, encoding="utf-8")
    after_path.write_text(after_csv, encoding="utf-8")
    return before_path, after_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic, non-proprietary EdgeConnect before/after CSV files "
            "for demo deployments."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Target directory to write subnetsExample_beforeChange.csv and subnetsExample_afterChange.csv",
    )
    parser.add_argument(
        "--appliance",
        default=DEFAULT_APPLIANCE,
        help="Synthetic appliance hostname recorded in the Appliance column",
    )
    args = parser.parse_args()
    before_path, after_path = write_synthetic_sample_data(args.output_dir, appliance=args.appliance)
    print(f"Generated synthetic sample CSVs:\n  - {before_path}\n  - {after_path}")


if __name__ == "__main__":
    main()
