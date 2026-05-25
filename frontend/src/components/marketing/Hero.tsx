"use client";

import {
  heroMarket,
  heroStats,
  heroFeedInitial,
  heroFeedPool,
} from "@/lib/mock-data";
import { useLiveFeed } from "@/lib/hooks/useLiveFeed";
import { useProbabilityNudge } from "@/lib/hooks/useProbabilityNudge";

export function Hero() {
  const feed = useLiveFeed(heroFeedInitial, heroFeedPool, 3, 3800);
  const { rounded, delta } = useProbabilityNudge(heroMarket.probability, 1.1, 2600);
  const up = delta >= 0;

  return (
    <div className="hero">
      <div className="glow" />
      <div className="vig" />
      <div className="hero-in wrap">
        <div>
          <span className="pill">
            <span className="dot" />
            The prediction layer · preview
          </span>
          <h1 className="hero-title">The prediction layer for the real world.</h1>
          <p className="hero-lead">
            Aggregate the world&apos;s markets, launch your own, and give people a
            place to prove they were right — on infrastructure that rebrands in a
            single line.
          </p>
          <div className="btns">
            <a className="btn btn-primary" href="#">
              Explore markets
            </a>
            <a className="btn" href="#">
              For partners →
            </a>
          </div>
          <div className="hstats">
            {heroStats.map((s) => (
              <div key={s.label}>
                <b>{s.value}</b>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="hero-panel-wrap">
          <div className="card">
            <div className="card-top">
              <span className="chip">{heroMarket.category}</span>
              <span className="live">
                <span className="dot" />
                PREVIEW
              </span>
            </div>
            <div className="q" style={{ minHeight: "auto" }}>
              {heroMarket.question}
            </div>
            <div className="prob">
              <div className="big">
                {rounded}
                <span>%</span>
              </div>
              <div className="lab">chance of Yes</div>
              <div className={`delta${up ? "" : " dn"}`}>
                {up ? "▲" : "▼"} {Math.abs(delta).toFixed(1)} pts
              </div>
            </div>
            <div className="track">
              <i style={{ width: `${rounded}%` }} />
            </div>
            <div className="feed">
              <div className="flab">Sample activity</div>
              {feed.map((r) => (
                <div className={`it${r.isNew ? " new" : ""}`} key={r.key}>
                  <span className="av" />
                  <span>
                    <b>{r.user}</b> backed{" "}
                    <span className={r.side}>{r.side === "yes" ? "Yes" : "No"}</span> ·{" "}
                    {r.amount}
                  </span>
                  <time>{r.ts}</time>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
