import { tickerItems } from "@/lib/mock-data";

export function Ticker() {
  // Duplicate the set so the marquee loops seamlessly (-50% translate).
  const items = [...tickerItems, ...tickerItems];
  return (
    <div className="strip" aria-hidden>
      <div className="strip-track">
        {items.map((t, i) => (
          // Topic marquee only — no invented probabilities/deltas shown.
          <span className="tk" key={i}>
            <b>{t.label}</b>
          </span>
        ))}
      </div>
    </div>
  );
}
