"use client";

import { useEffect, useState } from "react";

/** Fake-realtime counter that ticks upward — for the live sensor feeling. */
export function useCountUp(start: number, stepMax = 7, intervalMs = 1300) {
  const [value, setValue] = useState(start);

  useEffect(() => {
    const id = setInterval(() => {
      setValue((v) => v + Math.floor(Math.random() * stepMax) + 1);
    }, intervalMs);
    return () => clearInterval(id);
  }, [stepMax, intervalMs]);

  return value;
}
