import { ActivityFeed } from "./ActivityFeed";
import { Leaderboard } from "./Leaderboard";

export function RealtimeIdentity() {
  return (
    <section>
      <div className="wrap">
        <div className="shead">
          <div>
            <div className="eyebrow">Realtime</div>
            <h2>A live signal layer</h2>
            <p>
              Every position streams in real time — and every call builds a track
              record worth following.
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
