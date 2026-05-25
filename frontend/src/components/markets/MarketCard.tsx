import type { Market } from "@/lib/mock-data";

interface MarketCardProps {
  market: Market;
  loading?: boolean;
}

export function MarketCard({ market, loading }: MarketCardProps) {
  const up = market.delta >= 0;
  return (
    <div className={`card${loading ? " loading" : ""}`}>
      <div className="card-inner">
        <div className="card-top">
          <span className="chip">{market.category}</span>
          {market.status === "live" ? (
            <span className="live">
              <span className="dot" />
              LIVE
            </span>
          ) : (
            <span className="closing">{market.closeLabel}</span>
          )}
        </div>
        <div className="q">{market.question}</div>
        <div className="prob">
          <div className="big">
            {market.probability}
            <span>%</span>
          </div>
          <div className="lab">Yes</div>
          <div className={`delta${up ? "" : " dn"}`}>
            {up ? "▲" : "▼"} {Math.abs(market.delta)}
          </div>
        </div>
        <div className="track">
          <i style={{ width: `${market.probability}%` }} />
        </div>
        <div className="foot">
          <span>
            Vol <b>{market.volume}</b>
          </span>
          <span>
            <b>{market.traders}</b> traders
          </span>
        </div>
      </div>
      {loading && (
        <div className="skel" aria-hidden>
          <span className="sl w40" />
          <span className="sl w90" />
          <span className="sl w65" />
          <span className="sl big-sl" />
          <span className="sl tr" />
        </div>
      )}
    </div>
  );
}
