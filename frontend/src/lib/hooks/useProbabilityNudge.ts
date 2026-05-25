"use client";

import { useEffect, useState } from "react";

/** Gently nudges a probability around a base value for a live-pricing feel. */
export function useProbabilityNudge(base: number, amp = 1.1, intervalMs = 2600) {
  const [value, setValue] = useState(base);

  useEffect(() => {
    const id = setInterval(() => {
      const v = base + (Math.random() * amp * 2 - amp * 0.6);
      setValue(Math.round(v * 10) / 10);
    }, intervalMs);
    return () => clearInterval(id);
  }, [base, amp, intervalMs]);

  const delta = Math.round((value - base) * 10) / 10;
  return { value, delta, rounded: Math.round(value) };
}
