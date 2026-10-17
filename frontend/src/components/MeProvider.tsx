"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, type Me, type SiteRole } from "@/lib/api";

type MeState = {
  /** null until /api/me answers. */
  me: Me | null;
  signedIn: boolean;
  role: "admin" | "manager" | "crew" | null;
  /** The viewer's role on each site they're on. */
  siteRoles: Map<number, SiteRole>;
  refresh: () => Promise<void>;
};

const MeContext = createContext<MeState>({
  me: null,
  signedIn: false,
  role: null,
  siteRoles: new Map(),
  refresh: async () => {},
});

/** Loads who's signed in (and their sites) once for every page. Call `refresh` after changing memberships. */
export function MeProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      setMe({ user: null, sites: [], auth: "auth0" });
    }
  }, []);

  useEffect(() => {
    // Load once on mount; the state update happens after the request resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  const value = useMemo<MeState>(
    () => ({
      me,
      signedIn: !!me?.user,
      role: me?.user?.role ?? null,
      siteRoles: new Map((me?.sites ?? []).map((s) => [s.site_id, s.role])),
      refresh,
    }),
    [me, refresh],
  );
  return <MeContext.Provider value={value}>{children}</MeContext.Provider>;
}

export function useMe() {
  return useContext(MeContext);
}
