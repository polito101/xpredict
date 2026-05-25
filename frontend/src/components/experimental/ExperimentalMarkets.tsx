import { experimentalMarkets, type ExperimentalMarket } from "@/lib/mock-data";
import { Sparkline } from "./Sparkline";
import { TrafficCounter } from "./TrafficCounter";

function ExpIcon({ name }: { name: ExperimentalMarket["icon"] }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  switch (name) {
    case "traffic":
      return (
        <svg {...common}>
          <path d="M3 17h2l1-4h12l1 4h2" />
          <circle cx="7.5" cy="17.5" r="1.6" />
          <circle cx="16.5" cy="17.5" r="1.6" />
        </svg>
      );
    case "weather":
      return (
        <svg {...common}>
          <path d="M12 3v2M5 12H3M6.3 6.3 4.9 4.9M12 8a4 4 0 1 0 0 8" />
          <path d="M16 18h3a3 3 0 0 0 0-6 5 5 0 0 0-9.6-1.5" />
        </svg>
      );
    case "logistics":
      return (
        <svg {...common}>
          <rect x="3" y="8" width="18" height="11" rx="2" />
          <path d="M7 8V6a5 5 0 0 1 10 0v2M9 13h6" />
        </svg>
      );
    case "grid":
      return (
        <svg {...common}>
          <path d="M13 2 4 14h7l-1 8 9-12h-7z" />
        </svg>
      );
  }
}

export function ExperimentalMarkets() {
  return (
    <section className="exp">
      <div className="wrap">
        <div className="shead">
          <div>
            <div className="eyebrow">Experimental markets · beyond finance</div>
            <h2>Prediction, wired to the world.</h2>
            <p>
              The direction we&apos;re building toward: markets that read real-world
              signals — traffic, weather, logistics and power grids — not just
              opinions. Concept previews below.
            </p>
          </div>
          <span className="sigbadge">
            <span className="dot" />
            On the roadmap
          </span>
        </div>
        <div className="xgrid">
          {experimentalMarkets.map((m) => (
            <div className="xmkt" key={m.id}>
              <div className="scan" />
              <div className="xtop">
                <div className="xicon">
                  <ExpIcon name={m.icon} />
                </div>
                <span className="xlive">
                  <span className="dot" />
                  CONCEPT
                </span>
              </div>
              <div className="xq">{m.question}</div>
              {m.id === "i405-traffic" ? (
                <TrafficCounter start={17482} />
              ) : (
                <div className="xnum">{m.value}</div>
              )}
              <div className="lab" style={{ fontSize: "10.5px" }}>
                {m.valueLabel}
              </div>
              <Sparkline points={m.spark} />
              <div className="xmeta">
                <div className="src">
                  <b>Signal</b>
                  {m.source}
                </div>
                <div className="xprob">{m.probability}%</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
