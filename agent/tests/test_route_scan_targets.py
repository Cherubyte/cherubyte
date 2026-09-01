"""Per-subnet interface/on-link resolution, and skipping ARP for routed subnets.

ARP is link-local: it can never find a host that's reachable only through a
gateway, even though ping/IP routing works fine for it (see `_route_for`'s
docstring in scanner.py). These tests pin two things: (1) each configured
subnet resolves its own interface from the OS routing table, so a multi-NIC
box sweeps each subnet on the right interface, and (2) a subnet the routing
table says is off-link skips the doomed ARP broadcast (the ping + neighbour
table fallback still runs), with a one-time diagnostic explaining why.
"""

import pytest

from cherubyte_agent import scanner
from cherubyte_agent.scanner import _route_for, _scan_targets


@pytest.fixture(autouse=True)
def _clean():
    scanner.reset_scan_caches()
    yield
    scanner.reset_scan_caches()


def _fake_route(on_link_map):
    """Stand-in for scapy's conf.route.route(): given a destination IP, returns
    (iface, local_ip, gateway) the way the real routing table would — a
    non-zero gateway means the destination is reached through it, i.e. off-link."""

    def route(dest):
        for cidr, (iface, gw) in on_link_map.items():
            if scanner._in_subnet(dest, cidr):
                return iface, "0.0.0.0", gw
        return "eth0", "0.0.0.0", "0.0.0.0"

    return route


# --------------------------------------------------------------------- _route_for

def test_on_link_subnet_resolves_its_own_interface(monkeypatch):
    from scapy.all import conf

    monkeypatch.setattr(
        conf.route, "route", _fake_route({"192.168.1.0/24": ("eth0", "0.0.0.0")})
    )
    iface, on_link = _route_for("192.168.1.0/24")
    assert iface == "eth0"
    assert on_link is True


def test_routed_subnet_is_reported_off_link(monkeypatch):
    from scapy.all import conf

    monkeypatch.setattr(
        conf.route,
        "route",
        _fake_route({"192.168.80.0/24": ("eth0", "172.172.20.1")}),
    )
    iface, on_link = _route_for("192.168.80.0/24")
    assert iface == "eth0"
    assert on_link is False


def test_route_lookup_failure_assumes_on_link(monkeypatch):
    from scapy.all import conf

    def boom(dest):
        raise OSError("no route")

    monkeypatch.setattr(conf.route, "route", boom)
    iface, on_link = _route_for("10.0.0.0/24")
    assert iface is None
    assert on_link is True, "unknown routing must fall back to today's behaviour, not silently drop the subnet"


# ------------------------------------------------------------------- _scan_targets

def test_scan_targets_resolves_interface_per_subnet(monkeypatch):
    from scapy.all import conf

    monkeypatch.setattr(scanner.settings, "interface", "")
    monkeypatch.setattr(
        scanner.settings,
        "subnets",
        [{"cidr": "192.168.1.0/24"}, {"cidr": "192.168.80.0/24"}],
    )
    monkeypatch.setattr(
        conf.route,
        "route",
        _fake_route(
            {
                "192.168.1.0/24": ("eth0", "0.0.0.0"),
                "192.168.80.0/24": ("wlan0", "0.0.0.0"),
            }
        ),
    )
    targets = _scan_targets()
    assert ("192.168.1.0/24", "eth0") in targets
    assert ("192.168.80.0/24", "wlan0") in targets


def test_a_pinned_interface_overrides_per_subnet_routing(monkeypatch):
    from scapy.all import conf

    monkeypatch.setattr(scanner.settings, "interface", "eth1")
    monkeypatch.setattr(scanner.settings, "subnets", [{"cidr": "192.168.1.0/24"}])
    monkeypatch.setattr(
        conf.route, "route", _fake_route({"192.168.1.0/24": ("eth0", "0.0.0.0")})
    )
    targets = _scan_targets()
    assert targets == [("192.168.1.0/24", "eth1")]


# ------------------------------------------------------- _arp_scan / off-link skip

def _patch_arp_scan_dependencies(monkeypatch, on_link_map, srp_result=None):
    import scapy.all as scapy_all

    monkeypatch.setattr(scanner.settings, "interface", "")
    monkeypatch.setattr(scanner.settings, "enable_passive_arp", False)
    monkeypatch.setattr(scapy_all.conf.route, "route", _fake_route(on_link_map))
    monkeypatch.setattr(scapy_all, "srp", lambda *a, **kw: (srp_result or [], []))
    monkeypatch.setattr(scanner, "_ping_sweep", lambda *a, **kw: None)
    monkeypatch.setattr(scanner, "_neighbour_table", lambda: {})
    monkeypatch.setattr(scanner, "_local_host", lambda iface: None)


def test_off_link_subnet_skips_the_arp_broadcast(monkeypatch, caplog):
    monkeypatch.setattr(scanner.settings, "subnets", [{"cidr": "192.168.80.0/24"}])
    _patch_arp_scan_dependencies(
        monkeypatch, {"192.168.80.0/24": ("eth0", "172.172.20.1")}
    )

    called = False
    import scapy.all as scapy_all

    def fake_srp(*a, **kw):
        nonlocal called
        called = True
        return [], []

    monkeypatch.setattr(scapy_all, "srp", fake_srp)

    with caplog.at_level("WARNING"):
        hosts = scanner._arp_scan()

    assert called is False, "ARP is link-local; broadcasting to a routed subnet is pointless"
    assert hosts == []
    assert any("192.168.80.0/24" in r.message for r in caplog.records)


def test_an_on_link_subnet_is_still_swept_normally(monkeypatch):
    monkeypatch.setattr(scanner.settings, "subnets", [{"cidr": "192.168.1.0/24"}])
    _patch_arp_scan_dependencies(monkeypatch, {"192.168.1.0/24": ("eth0", "0.0.0.0")})

    import scapy.all as scapy_all

    calls = []
    monkeypatch.setattr(
        scapy_all, "srp", lambda *a, **kw: calls.append(True) or ([], [])
    )

    scanner._arp_scan()
    assert calls, "an on-link subnet must still be actively ARP-swept"


def test_the_off_link_warning_is_logged_only_once(monkeypatch, caplog):
    monkeypatch.setattr(scanner.settings, "subnets", [{"cidr": "192.168.80.0/24"}])
    _patch_arp_scan_dependencies(
        monkeypatch, {"192.168.80.0/24": ("eth0", "172.172.20.1")}
    )

    with caplog.at_level("WARNING"):
        scanner._arp_scan()
        scanner._arp_scan()

    warnings = [r for r in caplog.records if "192.168.80.0/24" in r.message]
    assert len(warnings) == 1
