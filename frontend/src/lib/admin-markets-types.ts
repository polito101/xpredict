/**
 * Plan 12-02 — Admin market-operations shared types.
 *
 * These type definitions live OUTSIDE `admin-markets-api.ts` because Next's
 * `"use server"` files may only export async functions (mirrors the
 * `admin-api.ts` / `admin-types.ts` split). Client components and Server
 * Actions both import the types from here.
 *
 * Shapes are transcribed verbatim from the verified backend contracts
 * (`backend/app/markets/schemas.py`, `backend/app/settlement/schemas.py`).
 *
 * THE TWO-PREFIX LANDMINE (Pitfall 1): market CRUD lives under
 * `/api/v1/admin/markets`, but resolve/reverse/force-settle are mounted at the
 * BARE `/admin/markets/{id}/...` prefix (no `/api/v1`). The wrappers in
 * `admin-markets-api.ts` encode that split; `admin-markets-api.test.ts` guards
 * it. These types are prefix-agnostic — they only describe the wire payloads.
 *
 * MONEY DISCIPLINE (CLAUDE.md hard constraint, SP-1): money/odds fields
 * (volume / volume_24hr / min_stake / max_stake / initial_odds / current_odds)
 * arrive from the backend as STRINGS (NUMERIC(18,4) / Numeric(8,6) serialized
 * via `Decimal -> str`). They are typed `string` here and rendered verbatim —
 * NEVER `parseFloat` / `Number()` for storage (floats lose precision).
 */

/** Generic paginated envelope returned by every admin list endpoint. */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/** The five market lifecycle states (UI-SPEC §Status badge palette). */
export type MarketStatus =
  | "OPEN"
  | "CLOSED"
  | "RESOLVED"
  | "CANCELLED"
  | "DRAFT";

/** The two market sources. */
export type MarketSource = "HOUSE" | "POLYMARKET";

/**
 * One outcome row (`OutcomeRead`, `markets/schemas.py:79-90`). Odds are STRINGS
 * on the wire (field_serializer `Decimal -> str`).
 */
export interface OutcomeRead {
  id: string;
  label: string;
  initial_odds: string; // odds — string, never a float
  current_odds: string; // odds — string, never a float
}

/**
 * Row shape from `GET /api/v1/admin/markets` (`MarketListItem`,
 * `markets/schemas.py:133-150`). `source_url` is derived server-side for
 * Polymarket markets (null for house). Money fields are strings (SP-1).
 */
export interface MarketListItem {
  id: string;
  question: string;
  slug: string;
  category: string | null;
  source: string;
  source_market_id: string | null;
  polymarket_slug: string | null;
  status: string;
  deadline: string;
  bet_count: number;
  created_at: string;
  volume: string; // money — string
  volume_24hr: string; // money — string
  source_url: string | null;
  outcomes: OutcomeRead[];
}

/**
 * Detail shape from `GET /api/v1/admin/markets/{id}` (`MarketRead`,
 * `markets/schemas.py:93-130`). Extends the list fields with the always-present
 * `resolution_criteria` plus the STL-06 resolution projection and the BET-06
 * stake limits (added on `MarketRead` by Plan 12-01). Resolution fields are
 * null until the market is RESOLVED; stake limits are null when the global
 * platform default applies.
 */
export interface MarketDetail {
  id: string;
  question: string;
  slug: string;
  resolution_criteria: string;
  category: string | null;
  source: string;
  source_market_id: string | null;
  status: string;
  deadline: string;
  bet_count: number;
  volume: string; // money — string
  volume_24hr: string; // money — string
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  resolved_at: string | null;
  // STL-06: the resolution projection exposed publicly on a RESOLVED market.
  winning_outcome_id: string | null;
  resolution_source: string | null; // "HOUSE" | "POLYMARKET_UMA"
  resolution_justification: string | null;
  // BET-06: per-market stake limits (NULL = the global default applies).
  min_stake: string | null; // money — string or null
  max_stake: string | null; // money — string or null
  outcomes: OutcomeRead[];
}

/** Convenience alias — the detail read IS the `MarketRead` shape. */
export type MarketRead = MarketDetail;

/**
 * Body for `POST /api/v1/admin/markets` (`MarketCreate`,
 * `markets/schemas.py:38-46`). `initial_odds_yes` defaults to "0.5" server-side
 * when omitted. Money/odds fields are strings (never `parseFloat` for storage).
 */
export interface MarketCreateBody {
  question: string;
  resolution_criteria: string;
  deadline: string; // ISO-8601, future
  initial_odds_yes?: string; // odds in (0,1) — string
  category?: string | null;
  // BET-06 per-market stake limits (optional; null/omitted = global default).
  min_stake?: string | null; // money — string
  max_stake?: string | null; // money — string
}

/**
 * Body for `PATCH /api/v1/admin/markets/{id}` (`MarketUpdate`,
 * `markets/schemas.py:58-65`). NOTE: the odds field here is `odds_yes`, NOT
 * `initial_odds_yes` as in create (verified backend discrepancy). All fields
 * optional (partial update).
 */
export interface MarketUpdateBody {
  resolution_criteria?: string;
  deadline?: string;
  odds_yes?: string; // odds in (0,1) — string
  category?: string | null;
  // BET-06 per-market stake limits (optional; null/omitted = global default).
  min_stake?: string | null; // money — string
  max_stake?: string | null; // money — string
}

/**
 * Body for `POST /admin/markets/{id}/resolve` (`ResolveMarketRequest`,
 * `settlement/schemas.py:22-28`). `extra="forbid"`, `justification` min_length=1.
 */
export interface ResolveMarketBody {
  winning_outcome_id: string;
  justification: string;
}

/**
 * Body for `POST /admin/markets/{id}/reverse` (`ReverseSettlementRequest`,
 * `settlement/schemas.py:61-66`). Justification only, `extra="forbid"`,
 * min_length=1.
 */
export interface ReverseBody {
  justification: string;
}

/**
 * Body for `POST /admin/markets/{id}/force-settle` (`ForceSettleRequest`,
 * `settlement/schemas.py:41-47`). Same shape as resolve, `extra="forbid"`.
 */
export interface ForceSettleBody {
  winning_outcome_id: string;
  justification: string;
}

/**
 * Query params for the admin market list (`GET /api/v1/admin/markets`,
 * `markets/router.py:52-77`). Backend filters are `source` / `status` /
 * `category`; pagination + sort follow the shared admin convention.
 */
export interface MarketListParams {
  source?: MarketSource | "";
  status?: MarketStatus | "";
  category?: string;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}
