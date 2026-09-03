"""Email (SMTP) notifications. Config comes from settings, overridable via DB.

Sends through the standard-library ``smtplib`` on a worker thread — the same
shell-out-rather-than-add-a-dependency choice as ``ping`` and ``snmpget``. A
multipart/alternative message carries both the plain-text body (the same lines
every other channel gets) and a branded HTML part built by ``render``.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from ..config import settings

logger = logging.getLogger("cherubyte.email")

SECURITY_MODES = ("starttls", "ssl", "none")

_runtime: dict[str, object] = {}


def configure(
    *,
    host: str | None = None,
    port: int | None = None,
    security: str | None = None,
    username: str | None = None,
    password: str | None = None,
    from_addr: str | None = None,
    to_addrs: str | None = None,
    enabled: bool | None = None,
) -> None:
    for key, value in (
        ("host", host),
        ("port", port),
        ("security", security),
        ("username", username),
        ("password", password),
        ("from_addr", from_addr),
        ("to_addrs", to_addrs),
        ("enabled", enabled),
    ):
        if value is not None:
            _runtime[key] = value


def _get(key: str, fallback: object) -> object:
    value = _runtime.get(key)
    return fallback if value is None else value


def host() -> str:
    return str(_get("host", settings.smtp_host) or "").strip()


def port() -> int:
    try:
        return int(_get("port", settings.smtp_port))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 587


def security() -> str:
    mode = str(_get("security", settings.smtp_security) or "starttls").strip().lower()
    return mode if mode in SECURITY_MODES else "starttls"


def _username() -> str:
    return str(_get("username", settings.smtp_username) or "").strip()


def _password() -> str:
    return str(_get("password", settings.smtp_password) or "")


def from_addr() -> str:
    explicit = str(_get("from_addr", settings.smtp_from) or "").strip()
    if explicit:
        return explicit
    # Fall back to the auth identity — most providers require From to match it.
    return _username()


def recipients() -> list[str]:
    raw = str(_get("to_addrs", settings.smtp_to) or "")
    return [addr for addr in (a.strip() for a in raw.replace(";", ",").split(",")) if addr]


def is_enabled() -> bool:
    return bool(_get("enabled", settings.smtp_enabled))


def has_auth() -> bool:
    return bool(_username() or _password())


def is_configured() -> bool:
    """Enabled AND has a server, a From address and at least one recipient."""
    return bool(is_enabled() and host() and from_addr() and recipients())


def _send_blocking(msg: EmailMessage) -> None:
    mode = security()
    timeout = 15
    if mode == "ssl":
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host(), port(), context=context, timeout=timeout) as smtp:
            if has_auth():
                smtp.login(_username(), _password())
            smtp.send_message(msg)
        return
    with smtplib.SMTP(host(), port(), timeout=timeout) as smtp:
        smtp.ehlo()
        if mode == "starttls":
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if has_auth():
            smtp.login(_username(), _password())
        smtp.send_message(msg)


async def send(subject: str, text: str, html: str | None = None) -> bool:
    if not is_configured():
        logger.debug("email not configured; skipping: %s", subject)
        return False

    msg = EmailMessage()
    name, addr = parseaddr(from_addr())
    msg["From"] = formataddr((name or "Cherubyte", addr or from_addr()))
    msg["To"] = ", ".join(recipients())
    msg["Subject"] = subject
    msg.set_content(text or subject)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        await asyncio.get_running_loop().run_in_executor(None, _send_blocking, msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("email send failed: %s", exc)
        return False


# --- HTML rendering -------------------------------------------------------

_PALETTE = {
    "bg": "#f2f2f5",
    "card": "#ffffff",
    "ink": "#171717",
    "muted": "#8e8e93",
    "edge": "#e2e2e6",
    "alert": "#c82626",
}

_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,Helvetica,Arial,"
    "sans-serif"
)


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render(title: str, lines: list[str], *, urgent: bool = False) -> str:
    """A branded HTML email in the panel's calm, near-monochrome style.

    All CSS is inline — mail clients strip ``<style>`` and never fetch a
    remote asset, so the wordmark is set as text, not an image.
    """
    p = _PALETTE
    accent = p["alert"] if urgent else p["ink"]

    body_rows = ""
    for raw in lines:
        line = raw.rstrip()
        if not line:
            body_rows += '<tr><td style="height:10px;line-height:10px">&nbsp;</td></tr>'
            continue
        indent = len(line) - len(line.lstrip())
        text = _esc(line.strip())
        pad = "padding-left:16px;" if indent else ""
        color = p["muted"] if indent else p["ink"]
        body_rows += (
            f'<tr><td style="{pad}padding-top:4px;padding-bottom:4px;'
            f"font-size:14px;line-height:1.5;color:{color};"
            f'font-family:{_FONT}">{text}</td></tr>'
        )

    return f"""\
<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="color-scheme" content="light"></head>
<body style="margin:0;padding:0;background:{p['bg']}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  style="background:{p['bg']};padding:32px 16px">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      style="max-width:480px;background:{p['card']};border-radius:16px;
      overflow:hidden">
      <tr><td style="padding:22px 28px 0 28px">
        <span style="font-family:{_FONT};font-size:13px;font-weight:600;
          letter-spacing:-0.01em;color:{p['muted']}">Cherubyte</span>
      </td></tr>
      <tr><td style="padding:6px 28px 0 28px">
        <div style="border-left:3px solid {accent};padding-left:12px">
          <h1 style="margin:0;font-family:{_FONT};font-size:18px;font-weight:600;
            letter-spacing:-0.011em;color:{p['ink']}">{_esc(title)}</h1>
        </div>
      </td></tr>
      <tr><td style="padding:14px 28px 24px 28px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          {body_rows}
        </table>
      </td></tr>
      <tr><td style="padding:14px 28px;border-top:1px solid {p['edge']}">
        <span style="font-family:{_FONT};font-size:11px;line-height:1.5;
          color:{p['muted']}">
          Sent by your Cherubyte panel. Change what emails you get in
          Settings &rsaquo; Notifications.
        </span>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""
