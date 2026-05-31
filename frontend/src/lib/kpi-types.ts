/**
 * Plan 10-04 — KPI dashboard wire types (plain, non-"use server" module).
 *
 * Mirrors the backend `KpiResponse` / `VolumeBucket` contract from Plan 10-02
 * (`backend/app/admin/kpi_schemas.py`). MONEY DISCIPLINE (CLAUDE.md hard
 * constraint + project money-as-string contract): every money field is typed
 * `string` on the wire and END TO END — it is NEVER `number`. The frontend
 * formats the string for DISPLAY ONLY (see kpi-card.tsx / volume-chart.tsx);
 * it must never `parseFloat`/`Number()` a money value for storage.
 *
 * A `"use server"` file (kpi-api.ts) may only export async functions, so these
 * shared types live here in a sibling plain module (Next constraint — same
 * split as admin-types.ts / branding-types.ts).
 */

export type KpiWindow = "24h" | "7d" | "30d";

/** One daily volume bucket for the 30-day chart. `volume` is a money STRING. */
export interface VolumeBucket {
  /** ISO timestamp at `date_trunc('day', ...)` granularity. */
  day: string;
  /** Money as string (never number). */
  volume: string;
}

/**
 * The single dashboard payload: five KPI cards + the 30-day volume buckets.
 * All money fields (`volume_24h`, `house_pnl_today`, `house_pnl_cumulative`)
 * are strings; `house_pnl_*` may be NEGATIVE (a leading "-"), which is valid.
 */
export interface KpiResponse {
  /** 24h bet volume — money string. */
  volume_24h: string;
  /** Distinct active users in the selected window. */
  daily_active_users: number;
  /** Markets with status OPEN. */
  active_markets: number;
  /** Markets past deadline awaiting resolution. */
  pending_resolutions: number;
  /** House P&L for the UTC calendar day — money string, may be negative. */
  house_pnl_today: string;
  /** House P&L all-time — money string, may be negative. */
  house_pnl_cumulative: string;
  /** ≤30 daily volume buckets; <1 → frontend empty state. */
  volume_buckets: VolumeBucket[];
}
