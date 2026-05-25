import { ActivityFeed } from "./ActivityFeed";
import { Leaderboard } from "./Leaderboard";

export function RealtimeIdentity() {
  return (
    <section>
      <div className="wrap">
        <div className="shead">
          <div>
            <div className="eyebrow">Preview</div>
            <h2>Reputation, built in</h2>
            <p>
              Positions stream as they happen, and every call builds a track record
              worth following. Sample preview — live once markets launch.
            </p>
          </div>
        </div>
        <div className="two">
          <ActivityFeed />
          <Leaderboard />
        </div>
      </div>
    </section>
  );
}
