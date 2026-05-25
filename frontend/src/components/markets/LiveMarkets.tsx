"use client";

import { useEffect, useState } from "react";
import { markets } from "@/lib/mock-data";
import { MarketCard } from "@/components/markets/MarketCard";

export function LiveMarkets() {
  // Skeleton -> resolve, staggered, for the cinematic load.
  const [ready, setReady] = useState(0);

  useEffect(() => {
    const timers = markets.map((_, i) =>
      setTimeout(() => setReady((n) => Math.max(n, i + 1)), 550 + i * 150)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <section>
      <div className="wrap">
        <div className="shead">
          <div>
            <div className="eyebrow">Live markets</div>
            <h2>What the world is pricing right now</h2>
            <p>
              Real-time probabilities, aggregated and native — every source
              normalized into one clean feed.
            </p>
          </div>
        </div>
        <div className="mkt-grid">
          {markets.map((m, i) => (
            <MarketCard key={m.id} market={m} loading={i >= ready} />
          ))}
        </div>
      </div>
    </section>
  );
}
