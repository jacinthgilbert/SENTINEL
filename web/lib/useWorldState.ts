"use client";

import { useEffect, useRef, useState } from "react";

export type WorldState = {
  t: string;
  tick: number;
  rainfall_mm_hr: number;
  stages: Record<string, number>;
  blocked_roads: number[];
  reports: unknown[];
  mode: "live" | "scenario";
};

/** The offline ladder (plan §4.4), reduced to what Step 1 can observe. */
export type Status = "connecting" | "live" | "stale" | "offline";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const STALE_AFTER_MS = 4000;
const OFFLINE_AFTER_MS = 12000;

export function useWorldState() {
  const [state, setState] = useState<WorldState | null>(null);
  const [status, setStatus] = useState<Status>("connecting");
  const lastSeen = useRef<number>(0);

  useEffect(() => {
    // EventSource reconnects on its own; we only classify freshness.
    const es = new EventSource(`${API}/events`);

    es.onmessage = (e) => {
      lastSeen.current = Date.now();
      setState(JSON.parse(e.data) as WorldState);
      setStatus("live");
    };
    es.onerror = () => {
      if (!lastSeen.current) setStatus("connecting");
    };

    const timer = setInterval(() => {
      if (!lastSeen.current) return;
      const age = Date.now() - lastSeen.current;
      if (age > OFFLINE_AFTER_MS) setStatus("offline");
      else if (age > STALE_AFTER_MS) setStatus("stale");
    }, 1000);

    return () => {
      clearInterval(timer);
      es.close();
    };
  }, []);

  const ageMs = lastSeen.current ? Date.now() - lastSeen.current : null;
  return { state, status, ageMs };
}
