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
    (("yealink", "grandstream", "polycom", "snom", "fanvil", "avaya", "mitel"), DeviceType.voip),
    (("irobot", "roborock", "ecovacs", "dreame", "3irobotix", "trifo"), DeviceType.vacuum),
    (("ecobee", "tado", "netatmo", "resideo"), DeviceType.thermostat),
    (("bsh hausger", "miele", "electrolux", "whirlpool", "haier", "midea", "sub-zero"), DeviceType.appliance),
    (("rakuten kobo", "remarkable"), DeviceType.ereader),
    (("lutron",), DeviceType.hub),
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
    # specific gadgets first — their names would otherwise be caught by a
    # broader rule below (e.g. "epson-eb" projector by the "epson" printer rule)
    (("kindle", "kobo", "remarkable", "pocketbook", "onyx-boox", "boox-", "-nook"), DeviceType.ereader),
    (("yealink", "grandstream", "polycom", "snom", "fanvil", "gigaset", "sip-", "-voip", "voip-", "cisco-cp"), DeviceType.voip),
    (("roomba", "roborock", "deebot", "braava", "-vacuum", "vacuum-", "dreame"), DeviceType.vacuum),
    (("projector", "beamer", "xgimi", "optoma", "epson-eb", "epson-tw", "epson-projector", "nebula-", "benq-w"), DeviceType.projector),
    (("hue-bridge", "philips-hue", "hue-bs", "smartthings", "aqara-hub", "lumi-gateway", "deconz", "conbee",
      "hubitat", "homey", "homebridge", "zigbee2mqtt", "-bridge", "bridge-", "zwave", "z-wave"), DeviceType.hub),
    (("thermostat", "ecobee", "tado", "nest-thermo", "wiser-heat"), DeviceType.thermostat),
    (("fridge", "refrigerator", "freezer", "washer", "washing-machine", "dishwasher", "dryer", "-oven",
      "oven-", "cooktop", "microwave", "homeconnect", "home-connect", "thinq"), DeviceType.appliance),
    (("doorbell", "nest-hello", "nesthello", "ring-", "-ring", "video-doorbell"), DeviceType.doorbell),
    (("nest-hub", "nest hub", "home-hub", "home hub", "echo-show", "echo show", "smart-display", "smart display"), DeviceType.display),
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
    (("cam", "camera"), DeviceType.camera),
    (("desktop", "-pc"), DeviceType.pc),
    (("laptop", "notebook"), DeviceType.laptop),
]

_PORT_HINTS: list[tuple[frozenset[int], DeviceType]] = [
    (frozenset({9100, 515, 631}), DeviceType.printer),
    (frozenset({554}), DeviceType.camera),
    (frozenset({5060, 5061}), DeviceType.voip),   # SIP
    (frozenset({8009}), DeviceType.tv),
    (frozenset({32400}), DeviceType.nas),
    (frozenset({3389}), DeviceType.pc),
    (frozenset({62078}), DeviceType.phone),
]


# mDNS service type -> device type (only reasonably strong signals)
_MDNS_HINTS: list[tuple[tuple[str, ...], DeviceType]] = [
    (("_printer", "_ipp", "_ipps", "_pdl-datastream"), DeviceType.printer),
    (("_hue",), DeviceType.hub),
    (("_googlecast", "_airplay", "_raop", "_nvstream", "_amzn-wplay"), DeviceType.media),
    (("_sonos", "_spotify-connect"), DeviceType.speaker),
    (("_hap", "_homekit", "_matter", "_esphomelib", "_miio"), DeviceType.iot),
    (("_adisk",), DeviceType.nas),
]

# When a device advertising a generic smart-home service (_hap / _miio / …) also
# carries one of these names, it is more than "iot" — refine it.
_IOT_BY_NAME: list[tuple[tuple[str, ...], DeviceType]] = [
    (("roomba", "roborock", "deebot", "braava", "vacuum"), DeviceType.vacuum),
    (("thermostat", "ecobee", "tado"), DeviceType.thermostat),
    (("hue", "smartthings", "aqara", "deconz", "conbee", "hubitat", "homey", "zigbee"), DeviceType.hub),
    (("doorbell", "nest-hello"), DeviceType.doorbell),
]

# Smart displays advertise a cast service, so the media rule would claim them.
_DISPLAY_NAMES = ("nest hub", "nest-hub", "home hub", "home-hub", "echo show", "echo-show",
                  "smart display", "smart-display")

# HTTP Server header substring -> device type
_HTTP_HINTS: list[tuple[tuple[str, ...], DeviceType]] = [
    (("routeros", "openwrt", "dd-wrt", "lighttpd/1.4.35", "mini_httpd"), DeviceType.router),
    (("hp http server", "cups", "kyocera", "brother", "epson"), DeviceType.printer),
    (("synology", "qnap", "nas"), DeviceType.nas),
    (("hikvision", "dahua", "webcam", "gstreamer"), DeviceType.camera),
    (("yealink", "grandstream", "snom", "mitel"), DeviceType.voip),
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
                if any(k in haystack for k in _DISPLAY_NAMES):
                    return DeviceType.display
                if any(k in haystack for k in ("apple tv", "apple-tv", "appletv", "shield", "chromecast", "fire tv")):
                    return DeviceType.media
                if "tv" in haystack or _tv_brand:
                    return DeviceType.tv
            if dtype == DeviceType.iot:
                for names, refined in _IOT_BY_NAME:
                    if any(k in haystack for k in names):
                        return refined
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
    DeviceType.hub: "network",
    DeviceType.pc: "monitor",
    DeviceType.laptop: "laptop",
    DeviceType.server: "server",
    DeviceType.phone: "smartphone",
    DeviceType.voip: "phone-call",
    DeviceType.tablet: "tablet",
    DeviceType.ereader: "book-open",
    DeviceType.wearable: "watch",
    DeviceType.tv: "tv",
    DeviceType.projector: "projector",
    DeviceType.media: "cast",
    DeviceType.display: "monitor-speaker",
    DeviceType.console: "gamepad-2",
    DeviceType.speaker: "speaker",
    DeviceType.printer: "printer",
    DeviceType.nas: "hard-drive",
    DeviceType.iot: "cpu",
    DeviceType.thermostat: "thermometer",
    DeviceType.appliance: "washing-machine",
    DeviceType.vacuum: "bot",
    DeviceType.camera: "cctv",
    DeviceType.doorbell: "bell-ring",
    DeviceType.car: "car",
}
