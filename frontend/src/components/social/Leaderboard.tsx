import { leaderboard } from "@/lib/mock-data";

export function Leaderboard() {
  return (
    <div className="panel">
      <h3>Top forecasters</h3>
      <p className="pc">Sample preview · ranked by accuracy at launch</p>
      {leaderboard.slice(0, 3).map((f) => (
        <div className="lead-row" key={f.rank}>
          <span className="rank">{f.rank}</span>
          <span className="av">{f.initials}</span>
          <div>
            <div className="nm">{f.user}</div>
            {/* No invented track record — real stats arrive when markets launch. */}
            <div className="sub">Sample forecaster</div>
          </div>
          <div className="acc-stat">
            <b>—</b>
            <span>at launch</span>
          </div>
        </div>
      ))}
    </div>
  );
}
