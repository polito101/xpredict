/**
 * Casino (demo) API types + fetch helper (quick task 260611-u0q).
 *
 * Mirrors `lib/catalog.ts`: the same `apiBase()` server/browser split and a
 * `cache:"no-store"` read. Consumes the public backend proxy:
 *   GET /api/v1/casino/games -> CasinoCatalog ({ status, games[] })
 *
 * The backend NEVER 500s this surface — every upstream failure (subscription off,
 * network, garbage) degrades to `{ status: "inactive", games: [] }`. This helper
 * mirrors that contract: a non-ok response (or a throw) returns the inactive shape,
 * so the page renders a friendly empty state and never crashes into an error
 * boundary. The token never reaches the browser as a raw env var — it appears only
 * inside the backend-composed `iframe_url`.
 */

/** One demo-slot tile. `iframe_url` is the backend-composed launch URL (carries the token). */
export interface CasinoGame {
  id: string;
  name: string;
  provider: string | null;
  thumb: string | null;
  iframe_url: string;
}

/** The `GET /api/v1/casino/games` payload — status discriminator + game list. */
export interface CasinoCatalog {
  status: "active" | "inactive";
  games: CasinoGame[];
}

/** The graceful degraded surface — reused for every fetch failure. */
const INACTIVE: CasinoCatalog = { status: "inactive", games: [] };

/**
 * Backend base for the current execution context (identical to `lib/catalog.ts`):
 * server-side → `BACKEND_URL` (Docker-internal) → `NEXT_PUBLIC_API_URL` → localhost;
 * browser → `NEXT_PUBLIC_API_URL` → localhost. The split is load-bearing under the
 * dockerized dev stack (a browser can't resolve the `backend` hostname).
 */
function apiBase(): string {
  if (typeof window === "undefined") {
    return (
      process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000"
    );
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/**
 * Fetches the demo-slots catalog. Returns the typed `CasinoCatalog`; on a non-ok
 * response OR any thrown error, returns `{ status: "inactive", games: [] }` so the
 * page degrades to its friendly empty state and never throws into the render.
 */
export async function fetchCasinoGames(): Promise<CasinoCatalog> {
  try {
    const res = await fetch(`${apiBase()}/api/v1/casino/games`, {
      cache: "no-store",
    });
    if (!res.ok) {
      return INACTIVE;
    }
    return (await res.json()) as CasinoCatalog;
  } catch {
    return INACTIVE;
  }
}
