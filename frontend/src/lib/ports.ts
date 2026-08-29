/** Turn an open port into something the user can act on from the browser. */
import type { MessageKey } from "../i18n/en";

export type PortAction =
  | { kind: "web"; href: string; hint: MessageKey }
  | { kind: "scheme"; href: string; hint: MessageKey }
  | { kind: "rdp"; host: string; hint: MessageKey }
  | { kind: "copy"; text: string; hint: MessageKey };

// ports that serve a web UI (probed service name may also just contain "http")
const WEB_PORTS = new Set([
  80, 280, 443, 591, 631, 1880, 2375, 2376, 3000, 3001, 5000, 5001, 5601, 7001,
  8000, 8006, 8008, 8042, 8080, 8081, 8085, 8088, 8123, 8443, 8444, 8843, 8880,
  8888, 9000, 9001, 9090, 9443, 19999, 32400,
]);
const HTTPS_PORTS = new Set([443, 8443, 8444, 8843, 9443]);

export function portAction(
  ip: string,
  port: number,
  service: string | null,
): PortAction {
  const svc = (service ?? "").toLowerCase();
  const isWeb = WEB_PORTS.has(port) || svc.includes("http") || svc === "ipp";

  if (isWeb) {
    const scheme = HTTPS_PORTS.has(port) || svc.includes("https") ? "https" : "http";
    const path = port === 32400 ? "/web" : "";
    return { kind: "web", href: `${scheme}://${ip}:${port}${path}`, hint: "port.web" };
  }

  if (port === 22 || svc === "ssh")
    return { kind: "scheme", href: `ssh://${ip}:${port}`, hint: "port.ssh" };
  if (port === 3389 || svc === "rdp")
    return { kind: "rdp", host: ip, hint: "port.rdp" };
  if (port === 5900 || port === 5901 || svc === "vnc")
    return { kind: "scheme", href: `vnc://${ip}:${port}`, hint: "port.vnc" };
  if (port === 445 || port === 139 || svc === "smb" || svc === "netbios")
    return { kind: "scheme", href: `smb://${ip}`, hint: "port.smb" };
  if (port === 554 || svc === "rtsp")
    return { kind: "scheme", href: `rtsp://${ip}:${port}`, hint: "port.rtsp" };
  if (port === 21 || svc === "ftp")
    return { kind: "scheme", href: `ftp://${ip}:${port}`, hint: "port.ftp" };
  if (port === 23 || svc === "telnet")
    return { kind: "scheme", href: `telnet://${ip}:${port}`, hint: "port.telnet" };

  return { kind: "copy", text: `${ip}:${port}`, hint: "port.copy" };
}

/** Windows/macOS RDP clients open a downloaded .rdp file directly. */
export function downloadRdp(host: string): void {
  const body = `full address:s:${host}\nprompt for credentials:i:1\nscreen mode id:i:2\n`;
  const url = URL.createObjectURL(new Blob([body], { type: "application/x-rdp" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${host}.rdp`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Clipboard copy that also works on a plain-http LAN origin. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* fall through */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    if (ok) return true;
  } catch {
    /* fall through */
  }
  window.prompt("Copiar:", text);
  return false;
}
