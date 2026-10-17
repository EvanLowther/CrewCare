"use client";

import { useState } from "react";
import { useMe } from "@/components/MeProvider";

export type Scope = "mine" | "all";
const KEY = "planit.siteScope";

function saved(): Scope | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "mine" || v === "all" ? v : null;
  } catch {
    return null;
  }
}

/**
 * "My sites" vs "All sites" for the dashboard and alerts. Defaults to My sites for signed-in managers and crew who
 * are on at least one site; remembered on this device once changed. `available` is false when there's nothing
 * to filter to (signed out, or no sites yet).
 */
export function useSiteScope() {
  const { me, siteRoles, role } = useMe();
  const [choice, setChoice] = useState<Scope | null>(saved);
  const available = !!me?.user && siteRoles.size > 0;
  const scope: Scope = !available ? "all" : (choice ?? (role === "admin" ? "all" : "mine"));

  const setScope = (s: Scope) => {
    setChoice(s);
    try {
      localStorage.setItem(KEY, s);
    } catch {
      /* private mode */
    }
  };
  const includes = (siteId: number) => scope === "all" || siteRoles.has(siteId);
  return { scope, setScope, available, includes };
}
