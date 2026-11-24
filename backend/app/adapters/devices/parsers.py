"""Production-grade parsers for EdgeConnect CSV/JSON, Cisco NX-OS, Cisco IOS-XE, and plain CIDR."""

from __future__ import annotations

import csv
import io
import ipaddress
import re
from typing import Any

from app.adapters.devices.base import NormalizedRoute

# EdgeConnect Metric field pattern, e.g. "50 (AD:15, PP:7)" or "52 (AD:251)" or "40"
_EC_METRIC_RE = re.compile(
    r"^\s*(?P<metric>\d+)"
    r"(?:\s*\((?=.*AD:(?P<ad>\d+))?(?=.*PP:(?P<pp>\d+))?[^)]*\))?\s*$"
)

# Cisco NX-OS `show ip route` prefix header: "10.103.0.0/19, ubest/mbest: 1/0"
_NXOS_PREFIX_RE = re.compile(
    r"^(?P<prefix>\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s*,\s*ubest/mbest:",
    re.IGNORECASE,
)
# Cisco NX-OS next-hop line:
#   *via 10.255.0.1, Eth1/1, [20/0], 2d14h, bgp-65001, external, tag 65002
_NXOS_VIA_RE = re.compile(
    r"^\s*\*?via\s+(?P<nexthop>\S+?),"
    r"(?:\s*(?P<interface>[^,\[]+),)?"
    r"\s*\[(?P<ad>\d+)/(?P<metric>\d+)\],"
    r"\s*[^,]+,\s*(?P<protocol>[^,\n]+)",
    re.IGNORECASE,
)
_NXOS_VRF_RE = re.compile(r"IP Route Table for VRF\s+\"(?P<vrf>[^\"]+)\"", re.IGNORECASE)

# Cisco IOS / IOS-XE `show ip route` entry:
#   B    10.103.0.0/19 [20/100] via 192.168.10.1, 02:14:05, GigabitEthernet0/0
#   S*   0.0.0.0/0 [1/0] via 10.162.183.217, GigabitEthernet0/1
#   C    10.1.0.0/16 is directly connected, Loopback0
_IOS_PROTOCOL_MAP = {
    "C": "connected",
    "L": "local",
    "S": "static",
    "B": "bgp",
    "O": "ospf",
    "D": "eigrp",
    "R": "rip",
    "i": "isis",
}
_IOS_VIA_RE = re.compile(
    r"^(?P<code>[A-Za-z][A-Za-z0-9\*]*)\s+"
    r"(?P<prefix>\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s+"
    r"\[(?P<ad>\d+)/(?P<metric>\d+)\]\s+via\s+(?P<nexthop>\d{1,3}(?:\.\d{1,3}){3})"
    r"(?:,\s*[^,]+)?(?:,\s*(?P<interface>\S+))?",
)
_IOS_CONT_VIA_RE = re.compile(
    r"^\s+\[(?P<ad>\d+)/(?P<metric>\d+)\]\s+via\s+(?P<nexthop>\d{1,3}(?:\.\d{1,3}){3})"
    r"(?:,\s*[^,]+)?(?:,\s*(?P<interface>\S+))?",
)
_IOS_CONN_RE = re.compile(
    r"^(?P<code>[CL])\s+(?P<prefix>\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s+"
    r"is directly connected,\s*(?P<interface>\S+)",
)
_IOS_VRF_RE = re.compile(r"^Routing Table:\s*(?P<vrf>\S+)", re.IGNORECASE)
_PLAIN_CIDR_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b")


def canonicalize_prefix(raw: str) -> str:
    """Validate and convert a CIDR string to its canonical network form."""
    net = ipaddress.ip_network(raw.strip(), strict=False)
    return str(net)


def parse_edgeconnect_metric(raw_metric: str) -> tuple[int | None, int | None, int | None]:
    """Parse EdgeConnect metric text like ``50 (AD:15, PP:7)`` into (metric, ad, pp)."""
    cleaned = raw_metric.strip()
    if not cleaned:
        return None, None, None
    match = _EC_METRIC_RE.match(cleaned)
    if not match:
        # Fallback: extract first integer if any
        num_match = re.search(r"\d+", cleaned)
        metric = int(num_match.group()) if num_match else None
        ad_match = re.search(r"AD\s*:\s*(\d+)", cleaned, re.IGNORECASE)
        pp_match = re.search(r"PP\s*:\s*(\d+)", cleaned, re.IGNORECASE)
        return (
            metric,
            int(ad_match.group(1)) if ad_match else None,
            int(pp_match.group(1)) if pp_match else None,
        )
    metric = int(match.group("metric"))
    ad = int(match.group("ad")) if match.group("ad") else None
    pp = int(match.group("pp")) if match.group("pp") else None
    return metric, ad, pp


def infer_edgeconnect_protocol(
    admin_distance: int | None,
    next_hop: str,
    interface: str,
) -> str:
    """Infer route protocol from EdgeConnect AD and egress attributes."""
    if not next_hop and not interface:
        return "sdwan_overlay"
    if admin_distance == 1:
        return "static"
    if admin_distance == 0:
        return "connected"
    if admin_distance == 251:
        return "local_fallback"
    return "dynamic"


def parse_edgeconnect_csv(csv_text: str, default_vrf: str = "default") -> list[NormalizedRoute]:
    """Parse Aruba EdgeConnect / Silver Peak Orchestrator CSV exports (handles UTF-8 BOM)."""
    cleaned_text = csv_text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(cleaned_text))
    if not reader.fieldnames:
        return []

    # Normalize column headers so slight casing/spacing differences are tolerated.
    header_map = {h.strip().lower(): h for h in reader.fieldnames if h}
    subnet_col = (
        header_map.get("subnet/mask")
        or header_map.get("prefix")
        or header_map.get("subnet")
        or header_map.get("network")
    )
    if not subnet_col:
        raise ValueError(f"Unsupported CSV headers {reader.fieldnames}; expected 'Subnet/Mask' or 'Prefix'")

    appliance_col = header_map.get("appliance") or header_map.get("device")
    nexthop_col = header_map.get("next hop") or header_map.get("nexthop")
    interface_col = header_map.get("interface")
    metric_col = header_map.get("metric")
    vrf_col = header_map.get("vrf") or header_map.get("segment")

    routes: list[NormalizedRoute] = []
    for row in reader:
        raw_prefix = (row.get(subnet_col) or "").strip()
        if not raw_prefix or "/" not in raw_prefix:
            continue
        prefix = canonicalize_prefix(raw_prefix)
        next_hop = (row.get(nexthop_col) or "").strip() if nexthop_col else ""
        interface = (row.get(interface_col) or "").strip() if interface_col else ""
        raw_metric = (row.get(metric_col) or "").strip() if metric_col else ""
        appliance = (row.get(appliance_col) or "").strip() if appliance_col else ""
        vrf = ((row.get(vrf_col) or "").strip() if vrf_col else "") or default_vrf

        metric, ad, pp = parse_edgeconnect_metric(raw_metric)
        protocol = infer_edgeconnect_protocol(ad, next_hop, interface)
        routes.append(
            NormalizedRoute(
                prefix=prefix,
                vrf=vrf,
                next_hop=next_hop,
                interface=interface,
                protocol=protocol,
                admin_distance=ad,
                metric=metric,
                peer_priority=pp,
                raw_metric=raw_metric,
                appliance=appliance,
            )
        )
    return routes


def parse_edgeconnect_orchestrator_json(
    payload: dict[str, Any] | list[dict[str, Any]],
    appliance: str = "",
) -> list[NormalizedRoute]:
    """Parse Aruba Orchestrator REST API subnet/route JSON responses."""
    entries = payload if isinstance(payload, list) else payload.get("entries", payload.get("routes", []))
    routes: list[NormalizedRoute] = []
    for item in entries:
        raw_prefix = str(item.get("prefix") or item.get("subnet") or "").strip()
        if not raw_prefix or "/" not in raw_prefix:
            continue
        ad = int(item["ad"]) if item.get("ad") is not None else None
        metric = int(item["metric"]) if item.get("metric") is not None else None
        pp = int(item["peerPriority"]) if item.get("peerPriority") is not None else None
        next_hop = str(item.get("nexthop") or item.get("next_hop") or "").strip()
        interface = str(item.get("interface") or "").strip()
        raw_metric_parts = []
        if ad is not None:
            raw_metric_parts.append(f"AD:{ad}")
        if pp is not None:
            raw_metric_parts.append(f"PP:{pp}")
        raw_metric = (
            f"{metric} ({', '.join(raw_metric_parts)})"
            if metric is not None and raw_metric_parts
            else str(metric or "")
        )
        routes.append(
            NormalizedRoute(
                prefix=canonicalize_prefix(raw_prefix),
                vrf=str(item.get("segment") or item.get("vrf") or "default"),
                next_hop=next_hop,
                interface=interface,
                protocol=str(item.get("protocol") or infer_edgeconnect_protocol(ad, next_hop, interface)),
                admin_distance=ad,
                metric=metric,
                peer_priority=pp,
                raw_metric=raw_metric,
                appliance=str(item.get("appliance") or appliance),
            )
        )
    return routes


def parse_cisco_nxos_cli(cli_text: str, hostname: str = "") -> list[NormalizedRoute]:
    """Parse Cisco Nexus NX-OS ``show ip route vrf all`` CLI output."""
    routes: list[NormalizedRoute] = []
    current_vrf = "default"
    current_prefix: str | None = None

    for raw_line in cli_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        vrf_match = _NXOS_VRF_RE.search(line)
        if vrf_match:
            current_vrf = vrf_match.group("vrf").strip() or "default"
            current_prefix = None
            continue

        prefix_match = _NXOS_PREFIX_RE.match(line.strip())
        if prefix_match:
            current_prefix = canonicalize_prefix(prefix_match.group("prefix"))
            continue

        via_match = _NXOS_VIA_RE.match(line)
        if via_match and current_prefix:
            nexthop = via_match.group("nexthop").strip()
            interface = (via_match.group("interface") or "").strip()
            ad = int(via_match.group("ad"))
            metric = int(via_match.group("metric"))
            proto_raw = via_match.group("protocol").strip().lower()
            if proto_raw.startswith("bgp"):
                protocol = "bgp"
            elif proto_raw.startswith("ospf"):
                protocol = "ospf"
            elif proto_raw in ("direct", "local"):
                protocol = "connected"
            elif proto_raw == "static":
                protocol = "static"
            else:
                protocol = proto_raw
            if nexthop.lower().startswith("null"):
                interface = interface or nexthop
                nexthop = ""
            routes.append(
                NormalizedRoute(
                    prefix=current_prefix,
                    vrf=current_vrf,
                    next_hop=nexthop,
                    interface=interface,
                    protocol=protocol,
                    admin_distance=ad,
                    metric=metric,
                    peer_priority=None,
                    raw_metric=f"{metric} (AD:{ad}, {protocol.upper()})",
                    appliance=hostname,
                )
            )
    return routes


def parse_cisco_nxapi_json(payload: dict[str, Any], hostname: str = "") -> list[NormalizedRoute]:
    """Parse Cisco Nexus NX-API ``show ip route vrf all | json`` structured output."""
    routes: list[NormalizedRoute] = []
    table_vrf = payload.get("TABLE_vrf", {}).get("ROW_vrf", [])
    if isinstance(table_vrf, dict):
        table_vrf = [table_vrf]

    for vrf_row in table_vrf:
        vrf_name = str(vrf_row.get("vrf-name-out") or "default")
        addrf_rows = vrf_row.get("TABLE_addrf", {}).get("ROW_addrf", [])
        if isinstance(addrf_rows, dict):
            addrf_rows = [addrf_rows]
        for addrf in addrf_rows:
            prefix_rows = addrf.get("TABLE_prefix", {}).get("ROW_prefix", [])
            if isinstance(prefix_rows, dict):
                prefix_rows = [prefix_rows]
            for prow in prefix_rows:
                raw_prefix = str(prow.get("ipprefix") or "").strip()
                if not raw_prefix:
                    continue
                prefix = canonicalize_prefix(raw_prefix)
                path_rows = prow.get("TABLE_path", {}).get("ROW_path", [])
                if isinstance(path_rows, dict):
                    path_rows = [path_rows]
                for path in path_rows:
                    ad = int(path["pref"]) if path.get("pref") is not None else None
                    metric = int(path["metric"]) if path.get("metric") is not None else None
                    proto = str(path.get("clientname") or "unknown").lower()
                    routes.append(
                        NormalizedRoute(
                            prefix=prefix,
                            vrf=vrf_name,
                            next_hop=str(path.get("ipnexthop") or ""),
                            interface=str(path.get("ifname") or ""),
                            protocol=proto.split("-")[0],
                            admin_distance=ad,
                            metric=metric,
                            raw_metric=f"{metric} (AD:{ad}, {proto.upper()})"
                            if metric is not None and ad is not None
                            else "",
                            appliance=hostname,
                        )
                    )
    return routes


def parse_cisco_ios_cli(cli_text: str, hostname: str = "") -> list[NormalizedRoute]:
    """Parse Cisco IOS / IOS-XE ``show ip route`` CLI output."""
    routes: list[NormalizedRoute] = []
    current_vrf = "default"
    last_prefix: str | None = None
    last_protocol = "unknown"

    for raw_line in cli_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        vrf_match = _IOS_VRF_RE.match(line.strip())
        if vrf_match:
            current_vrf = vrf_match.group("vrf").strip() or "default"
            last_prefix = None
            continue

        conn_match = _IOS_CONN_RE.match(line.strip())
        if conn_match:
            code = conn_match.group("code")[0]
            prefix = canonicalize_prefix(conn_match.group("prefix"))
            last_prefix = prefix
            last_protocol = _IOS_PROTOCOL_MAP.get(code, "connected")
            routes.append(
                NormalizedRoute(
                    prefix=prefix,
                    vrf=current_vrf,
                    next_hop="",
                    interface=conn_match.group("interface").strip(),
                    protocol=last_protocol,
                    admin_distance=0,
                    metric=0,
                    raw_metric="0 (AD:0, CONNECTED)",
                    appliance=hostname,
                )
            )
            continue

        via_match = _IOS_VIA_RE.match(line.strip())
        if via_match:
            code = via_match.group("code")[0]
            prefix = canonicalize_prefix(via_match.group("prefix"))
            ad = int(via_match.group("ad"))
            metric = int(via_match.group("metric"))
            protocol = _IOS_PROTOCOL_MAP.get(code, "unknown")
            last_prefix = prefix
            last_protocol = protocol
            routes.append(
                NormalizedRoute(
                    prefix=prefix,
                    vrf=current_vrf,
                    next_hop=via_match.group("nexthop").strip(),
                    interface=(via_match.group("interface") or "").strip(),
                    protocol=protocol,
                    admin_distance=ad,
                    metric=metric,
                    raw_metric=f"{metric} (AD:{ad}, {protocol.upper()})",
                    appliance=hostname,
                )
            )
            continue

        cont_match = _IOS_CONT_VIA_RE.match(line)
        if cont_match and last_prefix:
            ad = int(cont_match.group("ad"))
            metric = int(cont_match.group("metric"))
            routes.append(
                NormalizedRoute(
                    prefix=last_prefix,
                    vrf=current_vrf,
                    next_hop=cont_match.group("nexthop").strip(),
                    interface=(cont_match.group("interface") or "").strip(),
                    protocol=last_protocol,
                    admin_distance=ad,
                    metric=metric,
                    raw_metric=f"{metric} (AD:{ad}, {last_protocol.upper()})",
                    appliance=hostname,
                )
            )

    return routes


def parse_plain_cidr_lines(raw_text: str, label: str = "") -> list[NormalizedRoute]:
    """Parse newline/comma separated CIDR prefixes (e.g. Feature 2 quick text input)."""
    routes: list[NormalizedRoute] = []
    for line in raw_text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        for match in _PLAIN_CIDR_RE.finditer(cleaned):
            routes.append(
                NormalizedRoute(
                    prefix=canonicalize_prefix(match.group(1)),
                    vrf="default",
                    protocol="manual",
                    appliance=label,
                )
            )
    return routes


def auto_parse_routing_text(raw_text: str, label: str = "") -> list[NormalizedRoute]:
    """Auto-detect and parse EdgeConnect CSV, Cisco NX-OS, Cisco IOS, or plain CIDR text."""
    stripped = raw_text.lstrip("\ufeff").strip()
    if not stripped:
        return []

    first_line = stripped.splitlines()[0].lower()
    if "subnet/mask" in first_line or ("prefix" in first_line and "," in first_line):
        return parse_edgeconnect_csv(stripped)
    if "ubest/mbest:" in stripped or "ip route table for vrf" in stripped.lower():
        return parse_cisco_nxos_cli(stripped, hostname=label)
    if re.search(
        r"^\s*[A-Za-z][A-Za-z0-9\*]*\s+\d+\.\d+\.\d+\.\d+/\d+\s+\[\d+/\d+\]", stripped, re.MULTILINE
    ):
        return parse_cisco_ios_cli(stripped, hostname=label)
    return parse_plain_cidr_lines(stripped, label=label)
