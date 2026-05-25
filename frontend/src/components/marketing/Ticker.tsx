import { tickerItems } from "@/lib/mock-data";

export function Ticker() {
  // Duplicate the set so the marquee loops seamlessly (-50% translate).
  const items = [...tickerItems, ...tickerItems];
  return (
    <div className="strip" aria-hidden>
      <div className="strip-track">
        {items.map((t, i) => {
          const up = t.delta >= 0;
          return (
            <span className="tk" key={i}>
              <b>{t.label}</b> <em>{t.prob}%</em>
              <em className={up ? "up" : "dn"}>
                {up ? "▲" : "▼"}
                {Math.abs(t.delta)}
              </em>
            </span>
          );
        })}
      </div>
    </div>
  );
}
