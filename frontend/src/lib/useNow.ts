"use client";

import { useEffect, useState } from "react";

/** Current time in ms, re-read every `intervalMs` (keeps render pure; drives countdowns and "now" markers). */
export function useNow(intervalMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
