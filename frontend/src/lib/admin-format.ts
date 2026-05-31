/**
 * Plan 08-03 — Admin CRM display formatters.
 *
 * MONEY DISCIPLINE (CLAUDE.md hard constraint): money values arrive as STRINGS
 * (NUMERIC(18,4)). These helpers format them for display using STRING
 * operations only — NEVER `parseFloat` / `Number()` — so the full 4-decimal
 * precision is preserved exactly as the backend serialized it.
 */

/**
 * Insert thousands separators into the integer part of a numeric string,
 * pad/truncate the fractional part to exactly `decimals` digits, and prefix
 * with `$`. Pure string manipulation — no float parsing.
 *
 * formatMoney("1500")        -> "$1,500.0000"
 * formatMoney("1500.5")      -> "$1,500.5000"
 * formatMoney("-100.1234")   -> "-$100.1234"
 * formatMoney("0")           -> "$0.0000"
 */
export function formatMoney(value: string, decimals = 4): string {
  if (value == null || value === "") return "$0." + "0".repeat(decimals);

  let sign = "";
  let rest = value.trim();
  if (rest.startsWith("-")) {
    sign = "-";
    rest = rest.slice(1);
  } else if (rest.startsWith("+")) {
    rest = rest.slice(1);
  }

  const [intRaw, fracRaw = ""] = rest.split(".");
  const intPart = intRaw === "" ? "0" : intRaw;

  // Thousands separators, applied to the integer digits from the right.
  const withSeparators = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  // Pad or truncate the fractional part to exactly `decimals` digits.
  const fracPart = (fracRaw + "0".repeat(decimals)).slice(0, decimals);

  return `${sign}$${withSeparators}${decimals > 0 ? "." + fracPart : ""}`;
}

/**
 * Signed money for transaction rows: a `+` for credits, `-` for debits,
 * preserving the string precision. `kind` drives the sign/colour at the call
 * site; this only handles the magnitude string.
 */
export function formatSignedAmount(
  amount: string,
  direction: "credit" | "debit",
  decimals = 4,
): string {
  const magnitude = formatMoney(amount.replace(/^[-+]/, ""), decimals);
  return direction === "credit" ? `+${magnitude}` : `-${magnitude}`;
}

/** Format an ISO timestamp as e.g. "May 25, 2026". Returns "—" if invalid. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(d);
}

/** Format an ISO timestamp as "MMM DD HH:mm:ss" (audit log). "—" if invalid. */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const datePart = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
  }).format(d);
  const timePart = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(d);
  return `${datePart} ${timePart}`;
}

/** Relative time like "2h ago" / "5d ago" / "just now". "—" if null/invalid. */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  const mon = Math.floor(day / 30);
  if (mon < 12) return `${mon}mo ago`;
  return `${Math.floor(mon / 12)}y ago`;
}

/** Truncate a string to `max` chars, appending an ellipsis when cut. */
export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max).trimEnd() + "…";
}
