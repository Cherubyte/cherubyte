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


# --- the newer device types -------------------------------------------------

def test_ereader_by_hostname():
    assert classify("Amazon Technologies", "kindle-abc", {}) == DeviceType.ereader
    assert classify(None, "Kobo-Clara", {}) == DeviceType.ereader


def test_voip_phone_by_sip_port_and_vendor():
    assert classify(None, None, {5060: "sip"}) == DeviceType.voip
    assert classify("Yealink(XIAMEN) Network", "desk-phone", {80: "http"}) == DeviceType.voip


def test_robot_vacuum_by_vendor_and_name():
    assert classify("Roborock", None, {}) == DeviceType.vacuum
    assert classify(None, "roomba-97f2", {}) == DeviceType.vacuum
    # a vacuum in the Xiaomi cloud still resolves past the generic _miio -> iot
    assert classify("Xiaomi", "roborock-s7", {}, mdns_services=["_miio"]) == DeviceType.vacuum


def test_projector_beats_the_epson_printer_rule():
    assert classify("Seiko Epson", "epson-eb-projector", {}) == DeviceType.projector


def test_smart_display_is_not_plain_media():
    assert (
        classify("Google", "Nest-Hub-Kitchen", {}, mdns_services=["_googlecast"])
        == DeviceType.display
    )


def test_hue_bridge_is_a_hub_not_iot():
    assert classify("Signify", "Philips-hue", {}, mdns_services=["_hue"]) == DeviceType.hub


def test_thermostat_by_vendor():
    assert classify("ecobee inc.", "downstairs", {}) == DeviceType.thermostat


def test_smart_appliance_by_vendor_and_name():
    assert classify("BSH Hausgeraete GmbH", None, {}) == DeviceType.appliance
    assert classify(None, "kitchen-dishwasher", {}) == DeviceType.appliance


def test_video_doorbell_is_its_own_type_not_camera():
    assert classify(None, "front-doorbell", {}) == DeviceType.doorbell
    assert classify(None, "nest-hello-abc", {}) == DeviceType.doorbell
    # a plain camera is unaffected
    assert classify(None, "garden-cam", {}) == DeviceType.camera


def test_virtual_machine_by_hypervisor_vendor():
    assert classify("VMware, Inc.", None, {}) == DeviceType.vm
    assert classify("innotek GmbH", None, {}) == DeviceType.vm
    assert classify("QEMU", None, {}) == DeviceType.vm
    assert classify("Xensource, Inc.", None, {}) == DeviceType.vm
    assert classify("Parallels, Inc.", None, {}) == DeviceType.vm
