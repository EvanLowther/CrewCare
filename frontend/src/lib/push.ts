// Phone and desktop push notifications (Web Push). Android and desktop browsers support it directly; iPhones only
// once the site is added to the Home Screen (iOS 16.4+). The service worker is public/sw.js.
import { api } from "./api";

export type PushState = "unsupported" | "needs-home-screen" | "denied" | "off" | "on";

export function isIos(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function isStandalone(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
}

function supported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function subscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return reg ? reg.pushManager.getSubscription() : null;
}

/** Where this device stands. Only call in the browser. */
export async function pushState(): Promise<PushState> {
  if (!supported()) return isIos() && !isStandalone() ? "needs-home-screen" : "unsupported";
  if (Notification.permission === "denied") return "denied";
  return (await subscription()) && Notification.permission === "granted" ? "on" : "off";
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/** Ask permission (call from a click), subscribe this device and tell the server. */
export async function enablePush(): Promise<PushState> {
  if (!supported()) return pushState();
  if ((await Notification.requestPermission()) !== "granted") return pushState();
  const { public_key } = await api.pushKey();
  if (!public_key) throw new Error("Push isn't set up on this server yet; you'll still get notifications while the site is open.");
  const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) }));
  const json = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
  await api.subscribePush({ endpoint: json.endpoint, keys: json.keys });
  return "on";
}

export async function disablePush(): Promise<PushState> {
  const sub = await subscription();
  if (sub) {
    await api.unsubscribePush(sub.endpoint).catch(() => {});
    await sub.unsubscribe();
  }
  return pushState();
}

/** Re-send this device's subscription after sign-in (it may belong to someone else on a shared browser). */
export async function refreshPushSubscription(): Promise<void> {
  if (!supported() || Notification.permission !== "granted") return;
  const sub = await subscription();
  if (!sub) return;
  const json = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
  await api.subscribePush({ endpoint: json.endpoint, keys: json.keys }).catch(() => {});
}
