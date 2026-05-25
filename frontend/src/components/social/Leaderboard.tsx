import { leaderboard } from "@/lib/mock-data";

export function Leaderboard() {
  return (
    <div className="panel">
      <h3>Top forecasters</h3>
      <p className="pc">Ranked by calibrated accuracy</p>
      {leaderboard.slice(0, 3).map((f) => (
        <div className="lead-row" key={f.rank}>
          <span className="rank">{f.rank}</span>
          <span className="av">{f.initials}</span>
          <div>
            <div className="nm">{f.user}</div>
            <div className="sub">
              {f.resolved} resolved · {f.streak} streak
            </div>
          </div>
          <div className="acc-stat">
            <b>{f.accuracy}%</b>
            <span>accuracy</span>
          </div>
        </div>
      ))}
    </div>
  );
}
