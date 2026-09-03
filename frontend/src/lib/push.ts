/**
 * Web Push wiring for the browser side.
 *
 * The panel generates the VAPID keypair and holds it; here we register the
 * service worker, ask the browser to subscribe with the panel's public key, and
 * hand the resulting subscription back to the panel to store. Everything is a
 * no-op on a browser without the APIs (older Safari, an insecure origin).
 */
import { api } from "../api/client";

export type PushState = "unsupported" | "denied" | "off" | "on";

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

async function registration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration("/");
  return existing ?? navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

export async function currentPushState(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  try {
    const reg = await navigator.serviceWorker.getRegistration("/");
    const sub = await reg?.pushManager.getSubscription();
    return sub ? "on" : "off";
  } catch {
    return "off";
  }
}

function urlBase64ToBytes(base64: string): ArrayBuffer {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes.buffer;
}

/** Ask for permission, subscribe, and register with the panel. Returns the new state. */
export async function enablePush(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "off";

  const { key } = await api.pushKey();
  if (!key) throw new Error("the panel has no VAPID key");

  const reg = await registration();
  await navigator.serviceWorker.ready;

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToBytes(key),
    });
  }

  const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
  await api.pushSubscribe({
    endpoint: json.endpoint ?? sub.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
  });
  return "on";
}

/** Unsubscribe this browser and tell the panel to forget it. */
export async function disablePush(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  try {
    const reg = await navigator.serviceWorker.getRegistration("/");
    const sub = await reg?.pushManager.getSubscription();
    if (sub) {
      await api.pushUnsubscribe({ endpoint: sub.endpoint }).catch(() => {});
      await sub.unsubscribe();
    }
  } catch {
    /* fall through — nothing to clean up */
  }
  return Notification.permission === "denied" ? "denied" : "off";
}

/** Register the SW early so a push can wake it even if Settings is never opened. */
export function registerServiceWorker(): void {
  if (!pushSupported()) return;
  navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
}
