"""Name selection and cleanup — Host.best_name decides what the user sees."""

from cherubyte_protocol import HostObservation

from app.models import Device, _generic_host, _short_vendor
from app.services.naming import best_name, clean_name


def h(**kw) -> HostObservation:
    return HostObservation(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.10", **kw)


def test_mdns_name_wins_over_reverse_dns():
    assert best_name(h(mdns_name="Sala", hostname="192-168-1-10")) == "Sala"


def test_generic_candidates_are_skipped():
    assert best_name(h(hostname="android-1a2b3c", ssdp_name="Frigorifico")) == "Frigorifico"


def test_falls_back_to_a_generic_name_when_nothing_else_exists():
    assert best_name(h(hostname="localhost")) == "localhost"


def test_llmnr_name_is_used_when_nothing_stronger_is_available():
    assert best_name(h(llmnr_name="DESKTOP-AB12")) == "DESKTOP-AB12"


def test_netbios_wins_over_llmnr():
    assert best_name(h(netbios_name="LAPTOP", llmnr_name="DESKTOP-AB12")) == "LAPTOP"


def test_no_signal_at_all():
    assert best_name(h()) is None


def test_clean_name_strips_raop_prefix_and_local_suffix():
    assert clean_name("AABBCCDDEEFF@Sala.local") == "Sala"


def test_clean_name_strips_trailing_mac():
    assert clean_name("Sonos [aa:bb:cc:dd:ee:ff]") == "Sonos"


def test_short_vendor_canonicalises():
    assert _short_vendor("Apple, Inc.") == "Apple"
    assert _short_vendor("TP-LINK TECHNOLOGIES CO.,LTD.") == "TP-Link"


def test_short_vendor_trims_noise_for_unknown_brands():
    assert _short_vendor("Acme Technologies Inc.") == "Acme"


def test_generic_host_detection():
    assert _generic_host("ESP-A1B2C3")
    assert _generic_host("192-168-1-4")
    assert not _generic_host("Sams-MacBook-Pro")


def test_default_label_prefers_a_meaningful_hostname():
    d = Device(hostname="Sams-MacBook", vendor="Apple, Inc.", model="MacBookPro18,3")
    assert d.default_label == "Sams-MacBook"


def test_default_label_falls_back_to_brand_and_model():
    d = Device(hostname="android-1a2b3c", vendor="Samsung", model="Galaxy S21")
    assert d.default_label == "Samsung Galaxy S21"


def test_default_label_does_not_repeat_the_brand():
    d = Device(hostname="android-1a2b3c", vendor="Apple", model="Apple TV 4K")
    assert d.default_label == "Apple TV 4K"


def test_default_label_falls_back_to_the_mac():
    from app.models import MacAddress

    d = Device(macs=[MacAddress(address="aa:bb:cc:dd:ee:ff")])
    assert d.default_label == "aa:bb:cc:dd:ee:ff"
