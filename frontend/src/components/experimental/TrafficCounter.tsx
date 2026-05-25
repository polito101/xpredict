"use client";

import { useCountUp } from "@/lib/hooks/useCountUp";

export function TrafficCounter({ start }: { start: number }) {
  const n = useCountUp(start, 7, 1300);
  return <div className="xnum">{n.toLocaleString("en-US")}</div>;
}
