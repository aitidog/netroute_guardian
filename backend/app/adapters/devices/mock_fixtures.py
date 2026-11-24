"""Realistic raw Cisco NX-OS and IOS-XE routing table fixtures parsed by production parsers."""

CISCO_NEXUS_BEFORE_CLI = """\
IP Route Table for VRF "default"
'*' denotes best ucast next-hop
'**' denotes best mcast next-hop

0.0.0.0/0, ubest/mbest: 1/0
    *via 10.255.0.1, Eth1/1, [1/0], 4w2d, static
10.1.0.0/16, ubest/mbest: 2/0
    *via 10.255.1.2, Eth1/2, [20/50], 1w3d, bgp-65001, external, tag 65100
    *via 10.255.1.6, Eth1/3, [20/50], 1w3d, bgp-65001, external, tag 65100
10.1.1.0/24, ubest/mbest: 1/0
    *via 10.255.1.2, Eth1/2, [20/50], 1w3d, bgp-65001, external, tag 65100
10.1.5.0/25, ubest/mbest: 1/0
    *via 10.255.1.2, Eth1/2, [20/50], 1w3d, bgp-65001, external, tag 65100
10.2.2.0/26, ubest/mbest: 1/0
    *via 10.255.2.2, Eth1/4, [110/20], 3d12h, ospf-1, intra
10.103.0.0/19, ubest/mbest: 2/0
    *via 10.255.10.1, Eth1/5, [20/10], 5d02h, bgp-65001, external, tag 65200
    *via 10.255.10.5, Eth1/6, [20/20], 5d02h, bgp-65001, external, tag 65200
10.126.112.0/20, ubest/mbest: 1/0
    *via 10.255.12.1, Eth1/7, [20/15], 2w1d, bgp-65001, external, tag 65300
10.127.0.0/16, ubest/mbest: 2/0
    *via 10.255.20.1, Eth1/8, [20/50], 3w0d, bgp-65001, external, tag 65400
    *via 10.255.20.5, Eth1/9, [20/100], 3w0d, bgp-65001, external, tag 65400
10.198.0.0/16, ubest/mbest: 1/0
    *via 10.255.30.1, Eth1/10, [20/30], 6d04h, bgp-65001, external, tag 65500
172.16.2.0/24, ubest/mbest: 1/0
    *via 10.255.40.1, Eth1/11, [110/10], 1w0d, ospf-1, intra
172.16.2.128/26, ubest/mbest: 1/0
    *via 10.255.40.1, Eth1/11, [110/10], 1w0d, ospf-1, intra
192.168.8.0/26, ubest/mbest: 1/0
    *via 10.255.50.1, Eth1/12, [1/0], 8w0d, static
"""

CISCO_NEXUS_AFTER_CLI = """\
IP Route Table for VRF "default"
'*' denotes best ucast next-hop
'**' denotes best mcast next-hop

0.0.0.0/0, ubest/mbest: 1/0
    *via 10.255.0.1, Eth1/1, [1/0], 4w2d, static
10.1.0.0/16, ubest/mbest: 2/0
    *via 10.255.1.2, Eth1/2, [20/50], 1w3d, bgp-65001, external, tag 65100
    *via 10.255.1.6, Eth1/3, [20/50], 1w3d, bgp-65001, external, tag 65100
10.1.1.0/24, ubest/mbest: 1/0
    *via 10.255.1.2, Eth1/2, [20/50], 1w3d, bgp-65001, external, tag 65100
10.1.5.0/25, ubest/mbest: 1/0
    *via 10.255.1.2, Eth1/2, [20/50], 1w3d, bgp-65001, external, tag 65100
10.2.2.0/26, ubest/mbest: 1/0
    *via 10.255.2.2, Eth1/4, [110/20], 3d12h, ospf-1, intra
10.103.0.0/19, ubest/mbest: 1/0
    *via 10.255.10.9, Eth1/6, [20/80], 00:04:12, bgp-65001, external, tag 65200
10.127.0.0/16, ubest/mbest: 1/0
    *via 10.255.20.5, Eth1/9, [20/100], 3w0d, bgp-65001, external, tag 65400
10.198.0.0/16, ubest/mbest: 1/0
    *via 10.255.30.1, Eth1/10, [20/30], 6d04h, bgp-65001, external, tag 65500
10.200.44.0/24, ubest/mbest: 1/0
    *via 10.255.60.1, Eth1/14, [110/15], 00:03:00, ospf-1, intra
172.16.2.0/24, ubest/mbest: 1/0
    *via 10.255.40.1, Eth1/11, [110/10], 1w0d, ospf-1, intra
172.16.2.128/26, ubest/mbest: 1/0
    *via 10.255.40.1, Eth1/11, [110/10], 1w0d, ospf-1, intra
192.168.8.0/26, ubest/mbest: 1/0
    *via 10.255.50.1, Eth1/12, [1/0], 8w0d, static
"""

CISCO_ROUTER_BEFORE_CLI = """\
Routing Table: default
Codes: L - local, C - connected, S - static, B - BGP, O - OSPF

S*   0.0.0.0/0 [1/0] via 198.51.100.1, GigabitEthernet0/0/0
C    10.1.0.0/16 is directly connected, GigabitEthernet0/0/1
O    10.1.1.0/24 [110/10] via 10.1.0.2, 5d02h, GigabitEthernet0/0/1
O    10.1.5.0/25 [110/15] via 10.1.0.2, 5d02h, GigabitEthernet0/0/1
O    10.2.2.0/26 [110/20] via 10.1.0.3, 2d10h, GigabitEthernet0/0/2
B    10.76.12.0/23 [20/50] via 198.51.100.10, 1w4d, GigabitEthernet0/0/0
B    10.130.0.0/17 [20/50] via 198.51.100.10, 1w4d, GigabitEthernet0/0/0
                   [20/150] via 198.51.100.14, 1w4d, GigabitEthernet0/0/3
B    172.16.2.0/24 [20/30] via 198.51.100.10, 6d11h, GigabitEthernet0/0/0
B    172.16.2.128/26 [20/30] via 198.51.100.10, 6d11h, GigabitEthernet0/0/0
S    192.168.8.0/26 [1/0] via 10.1.0.254, GigabitEthernet0/0/1
"""

CISCO_ROUTER_AFTER_CLI = """\
Routing Table: default
Codes: L - local, C - connected, S - static, B - BGP, O - OSPF

S*   0.0.0.0/0 [1/0] via 198.51.100.1, GigabitEthernet0/0/0
C    10.1.0.0/16 is directly connected, GigabitEthernet0/0/1
O    10.1.1.0/24 [110/10] via 10.1.0.2, 5d02h, GigabitEthernet0/0/1
O    10.1.5.0/25 [110/15] via 10.1.0.2, 5d02h, GigabitEthernet0/0/1
O    10.2.2.0/26 [110/20] via 10.1.0.3, 2d10h, GigabitEthernet0/0/2
B    10.76.12.0/23 [20/50] via 198.51.100.10, 1w4d, GigabitEthernet0/0/0
B    10.130.0.0/17 [20/150] via 198.51.100.14, 00:05:10, GigabitEthernet0/0/3
B    172.16.2.0/24 [20/30] via 198.51.100.10, 6d11h, GigabitEthernet0/0/0
B    172.16.2.128/26 [20/30] via 198.51.100.10, 6d11h, GigabitEthernet0/0/0
S    192.168.8.0/26 [1/0] via 10.1.0.254, GigabitEthernet0/0/1
"""
