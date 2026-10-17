// Who the browser is signed in as, for API calls (docs/AUTH.md).
// - Live site: Auth0. The access token comes from the Next server's /auth/access-token route and goes to the API as
//   "Authorization: Bearer <token>".
// - Laptops: NEXT_PUBLIC_AUTH_DEV=1 shows a "Sign in as" menu, and the API gets "Authorization: Dev <name>".
import { getAccessToken } from "@auth0/nextjs-auth0";

export const DEV_AUTH = process.env.NEXT_PUBLIC_AUTH_DEV === "1";

export const DEV_USERS = [
  { key: "admin", label: "Dev Admin", role: "admin" },
  { key: "manager", label: "Dev Manager", role: "manager" },
  { key: "manager2", label: "Dev Manager 2", role: "manager" },
  { key: "crew", label: "Dev Crew", role: "crew" },
  { key: "crew2", label: "Dev Crew 2", role: "crew" },
] as const;

const DEV_KEY = "planit.devUser";

export function devUser(): string | null {
  try {
    return localStorage.getItem(DEV_KEY);
  } catch {
    return null;
  }
}

/** Switch dev user (null = sign out) and reload so every page refetches as them. */
export function setDevUser(key: string | null) {
  try {
    if (key) localStorage.setItem(DEV_KEY, key);
    else localStorage.removeItem(DEV_KEY);
  } catch {
    /* private mode: nothing to remember */
  }
  window.location.reload();
}

export function signInHref(returnTo: string) {
  return `/auth/login?returnTo=${encodeURIComponent(returnTo)}`;
}
export const SIGN_OUT_HREF = "/auth/logout";

let cached: { token: string; expiresAt: number } | null = null;
let signedOut = false;
let pending: Promise<string | null> | null = null;

/** The Auth0 access token, cached until a minute before it expires; null when signed out. */
function auth0Token(): Promise<string | null> {
  if (signedOut) return Promise.resolve(null);
  if (cached && cached.expiresAt - 60 > Date.now() / 1000) return Promise.resolve(cached.token);
  pending ??= getAccessToken({ includeFullResponse: true })
    .then((r) => {
      cached = { token: r.token, expiresAt: r.expires_at ?? Date.now() / 1000 + 300 };
      return r.token;
    })
    .catch(() => {
      // No session (signing in reloads the page, so this resets then).
      signedOut = true;
      return null;
    })
    .finally(() => {
      pending = null;
    });
  return pending;
}

/** Headers that say who's calling, or {} when signed out (the API then shows public reference sites only). */
export async function authHeaders(): Promise<Record<string, string>> {
  if (typeof window === "undefined") return {};
  if (DEV_AUTH) {
    const user = devUser();
    return user ? { Authorization: `Dev ${user}` } : {};
  }
  const token = await auth0Token();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
