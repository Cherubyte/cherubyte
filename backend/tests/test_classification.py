"""Table tests for the device classifier — the file with the most branching
logic in the project and the easiest place for a regression to hide."""

from app.models import DeviceType
from app.services.enrichment import classify


def test_gateway_always_wins():
    assert classify("Apple", "iphone", {62078: "x"}, True) == DeviceType.router


def test_mdns_beats_ports():
    # a printer advertising IPP is a printer even with an http port open
    assert (
        classify(None, None, {80: "http"}, mdns_services=["_ipp"]) == DeviceType.printer
    )


def test_mac_advertising_airplay_stays_a_computer():
    # the _MDNS_HINTS media rule must not swallow laptops
    assert (
        classify("Apple", "Sams-MacBook-Pro", {22: "ssh"}, mdns_services=["_airplay"])
        == DeviceType.laptop
    )


def test_airplay_on_a_tv_brand_is_a_tv():
    assert (
        classify("LG Electronics", "living-room", {}, mdns_services=["_airplay"])
        == DeviceType.tv
    )


def test_airplay_on_an_apple_tv_is_media():
    assert (
        classify("Apple", "Apple TV", {}, mdns_services=["_airplay"]) == DeviceType.media
    )


def test_port_hints():
    assert classify(None, None, {9100: "jetdirect"}) == DeviceType.printer
    assert classify(None, None, {554: "rtsp"}) == DeviceType.camera
    assert classify(None, None, {62078: "apple-sync"}) == DeviceType.phone


def test_http_server_hint():
    assert classify(None, None, {80: "http"}, http_server="RouterOS") == DeviceType.router


def test_hostname_before_vendor():
    # Apple's vendor hint says phone; the hostname says laptop and should win
    assert classify("Apple, Inc.", "MacBook-Air", {}) == DeviceType.laptop


def test_ssh_plus_web_is_a_server():
    assert classify(None, None, {22: "ssh", 443: "https"}) == DeviceType.server


def test_unknown_when_nothing_matches():
    assert classify(None, None, {}) == DeviceType.unknown
