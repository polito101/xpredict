"use client";

import { useEffect, useState } from "react";

export interface FeedRow {
  key: number;
  user: string;
  side: "yes" | "no";
  amount: string;
  ts: string;
  isNew?: boolean;
}

interface SeedRow {
  user: string;
  side: "yes" | "no";
  amount: string;
  ts: string;
}
interface PoolRow {
  user: string;
  side: "yes" | "no";
  amount: string;
}

// Module-level monotonic id: never resets (HMR-safe and production-safe), so
// injected rows can never collide with existing React keys.
let uid = 1;

/** Periodically prepends a random row from the pool, trimming to `max`. */
export function useLiveFeed(seed: SeedRow[], pool: PoolRow[], max = 3, intervalMs = 3800) {
  const [rows, setRows] = useState<FeedRow[]>(() =>
    seed.slice(0, max).map((r) => ({ key: uid++, ...r }))
  );

  useEffect(() => {
    const id = setInterval(() => {
      const pick = pool[Math.floor(Math.random() * pool.length)];
      setRows((prev) => {
        const next: FeedRow[] = [
          { key: uid++, user: pick.user, side: pick.side, amount: pick.amount, ts: "now", isNew: true },
          ...prev.map((r) => ({ ...r, isNew: false })),
        ];
        return next.slice(0, max);
      });
    }, intervalMs);
    return () => clearInterval(id);
  }, [pool, max, intervalMs]);

  return rows;
}
