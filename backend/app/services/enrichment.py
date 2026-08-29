"""Heuristic device classification from vendor / hostname / open ports."""

from __future__ import annotations

from ..models import DeviceType

_VENDOR_HINTS: list[tuple[tuple[str, ...], DeviceType]] = [
    (("apple",), DeviceType.phone),
    (("samsung",), DeviceType.phone),
    (("xiaomi", "huawei", "oneplus", "oppo", "vivo", "realme"), DeviceType.phone),
    (("raspberry",), DeviceType.server),
    (("intel", "dell", "asus", "gigabyte", "msi", "lenovo", "hewlett"), DeviceType.pc),
    (("tp-link", "netgear", "ubiquiti", "mikrotik", "zyxel", "avm", "fritz"), DeviceType.router),
    (("hp inc", "canon", "epson", "brother", "lexmark"), DeviceType.printer),
    (("sony", "nintendo", "microsoft"), DeviceType.console),
    (("lg electronics", "vizio", "roku", "tcl"), DeviceType.tv),
    (("amazon",), DeviceType.speaker),
    (("google", "nest"), DeviceType.speaker),
    (("synology", "qnap", "western digital"), DeviceType.nas),
    (("espressif", "tuya", "sonos", "shelly", "signify", "philips lighting"), DeviceType.iot),
    (("hikvision", "dahua", "reolink", "axis"), DeviceType.camera),
]

_HOSTNAME_HINTS: list[tuple[tuple[str, ...], DeviceType]] = [
    (("iphone",), DeviceType.phone),
    (("ipad",), DeviceType.tablet),
    (("tab-s", "galaxy-tab", "-tab-", "sm-t", "mediapad", "lenovo-tb", "mi-pad"), DeviceType.tablet),
    (("macbook",), DeviceType.laptop),
    (("android",), DeviceType.phone),
    (("pixel-", "galaxy-s", "galaxy-a", "redmi", "poco", "sm-g", "sm-a", "oneplus"), DeviceType.phone),
    (("tv", "bravia", "aquos", "shield"), DeviceType.tv),
    (("chromecast",), DeviceType.tv),
    (("printer", "hpprinter", "epson", "canon"), DeviceType.printer),
    (("nas", "synology", "diskstation"), DeviceType.nas),
    (("raspberrypi", "raspi", "rpi-", "ubuntu", "debian", "server", "proxmox"), DeviceType.server),
    (("router", "gateway", "fritz", "openwrt", "fibergateway"), DeviceType.router),
    (("cam", "camera", "doorbell"), DeviceType.camera),
    (("desktop", "-pc"), DeviceType.pc),
    (("laptop", "notebook"), DeviceType.laptop),
]

_PORT_HINTS: list[tuple[frozenset[int], DeviceType]] = [
    (frozenset({9100, 515, 631}), DeviceType.printer),
    (frozenset({554}), DeviceType.camera),
    (frozenset({8009}), DeviceType.tv),
    (frozenset({32400}), DeviceType.nas),
    (frozenset({3389}), DeviceType.pc),
    (frozenset({62078}), DeviceType.phone),
]


# mDNS service type -> device type (only reasonably strong signals)
_MDNS_HINTS: list[tuple[tuple[str, ...], DeviceType]] = [
    (("_printer", "_ipp", "_ipps", "_pdl-datastream"), DeviceType.printer),
    (("_googlecast", "_airplay", "_raop", "_nvstream", "_amzn-wplay"), DeviceType.media),
    (("_sonos", "_spotify-connect"), DeviceType.speaker),
    (("_hap", "_homekit", "_matter", "_esphomelib", "_miio"), DeviceType.iot),
    (("_adisk",), DeviceType.nas),
]

# HTTP Server header substring -> device type
_HTTP_HINTS: list[tuple[tuple[str, ...], DeviceType]] = [
    (("routeros", "openwrt", "dd-wrt", "lighttpd/1.4.35", "mini_httpd"), DeviceType.router),
    (("hp http server", "cups", "kyocera", "brother", "epson"), DeviceType.printer),
    (("synology", "qnap", "nas"), DeviceType.nas),
    (("hikvision", "dahua", "webcam", "gstreamer"), DeviceType.camera),
]


def classify(
    vendor: str | None,
    hostname: str | None,
    open_ports: dict[int, str] | None,
    is_gateway: bool = False,
    *,
    mdns_services: list[str] | None = None,
    http_server: str | None = None,
    model: str | None = None,
) -> DeviceType:
    if is_gateway:
        return DeviceType.router

    haystack = f"{hostname or ''} {model or ''}".lower()
    vend = (vendor or "").lower()
    _tv_brand = any(
        b in vend
        for b in ("lg electronics", "sony", "samsung", "vizio", "tcl", "hisense",
                  "philips", "panasonic", "sharp", "roku", "sky", "sagemcom")
    )

    services = {s.lower() for s in (mdns_services or [])}
    _is_computer_name = any(
        k in haystack for k in ("macbook", "imac", "mac mini", "mac-", "laptop", "desktop", "-pc")
    )
    for needles, dtype in _MDNS_HINTS:
        if any(any(n in s for s in services) for n in needles):
            if dtype == DeviceType.media:
                if _is_computer_name:
                    continue  # a Mac advertising AirPlay is still a Mac
                if any(k in haystack for k in ("apple tv", "apple-tv", "appletv", "shield", "chromecast", "fire tv")):
                    return DeviceType.media
                if "tv" in haystack or _tv_brand:
                    return DeviceType.tv
            return dtype

    ports = set((open_ports or {}).keys())
    for port_set, dtype in _PORT_HINTS:
        if port_set & ports:
            return dtype

    srv = (http_server or "").lower()
    for needles, dtype in _HTTP_HINTS:
        if any(n in srv for n in needles):
            return dtype

    for needles, dtype in _HOSTNAME_HINTS:
        if any(n in haystack for n in needles):
            return dtype

    for needles, dtype in _VENDOR_HINTS:
        if any(n in vend for n in needles):
            return dtype

    if 22 in ports and (80 in ports or 443 in ports):
        return DeviceType.server
    return DeviceType.unknown


ICON_FOR_TYPE: dict[DeviceType, str] = {
    DeviceType.unknown: "help-circle",
    DeviceType.router: "router",
    DeviceType.ap: "wifi",
    DeviceType.pc: "monitor",
    DeviceType.laptop: "laptop",
    DeviceType.phone: "smartphone",
    DeviceType.tablet: "tablet",
    DeviceType.tv: "tv",
    DeviceType.media: "cast",
    DeviceType.console: "gamepad-2",
    DeviceType.printer: "printer",
    DeviceType.nas: "hard-drive",
    DeviceType.iot: "cpu",
    DeviceType.camera: "cctv",
    DeviceType.speaker: "speaker",
    DeviceType.wearable: "watch",
    DeviceType.server: "server",
    DeviceType.car: "car",
}
