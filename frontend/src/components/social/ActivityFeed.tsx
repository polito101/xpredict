import { initialActivity, type ActivityItem } from "@/lib/mock-data";

function ActivityBody({ a }: { a: ActivityItem }) {
  switch (a.action) {
    case "yes":
      return (
        <>
          backed <span className="yes">Yes</span> on <b>{a.detail}</b>
        </>
      );
    case "no":
      return (
        <>
          backed <span className="no">No</span> on <b>{a.detail}</b>
        </>
      );
    case "opened":
      return (
        <>
          opened a market · <b>{a.detail}</b>
        </>
      );
    case "resolved":
      return (
        <>
          resolved <span className="yes">correct</span> · <b>{a.detail}</b>
        </>
      );
  }
}

export function ActivityFeed() {
  return (
    <div className="panel">
      <h3>Activity</h3>
      <p className="pc">Sample preview · not live yet</p>
      {initialActivity.map((a) => (
        <div className="it" style={{ borderTop: "1px solid var(--line)" }} key={a.id}>
          <span className="av" />
          <span>
            <b>{a.user}</b> <ActivityBody a={a} />
          </span>
          <time>{a.ts}</time>
        </div>
      ))}
    </div>
  );
}
