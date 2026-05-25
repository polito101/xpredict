export function Sparkline({ points }: { points: number[] }) {
  const step = 120 / (points.length - 1);
  const d = points.map((y, i) => `${(i * step).toFixed(1)},${y}`).join(" ");
  return (
    <svg className="spark" viewBox="0 0 120 30" preserveAspectRatio="none" aria-hidden>
      <polyline
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={d}
      />
    </svg>
  );
}
