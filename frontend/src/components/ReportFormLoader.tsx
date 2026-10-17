"use client";

import dynamic from "next/dynamic";

// The form reads browser-only state (secure context, geolocation, saved name) on its first render, so it
// renders in the browser only; the server sends this placeholder.
export const ReportFormLoader = dynamic(() => import("./ReportForm").then((m) => m.ReportForm), {
  ssr: false,
  loading: () => <p className="text-sm text-muted">Loading report form…</p>,
});
