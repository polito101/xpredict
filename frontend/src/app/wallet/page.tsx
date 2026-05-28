/**
 * Plan 03-05 Task 3 — Player wallet page (WAL-03 balance, WAL-04 history, SC#6 stub).
 *
 * A Server Component that shows the logged-in player:
 *   - their current play balance (in PLAY_USD),
 *   - their recent transaction history (empty-state when there is none), and
 *   - a DISABLED "Add funds" button (SC#6 / PLT-05) — the Stripe top-up
 *     affordance is present but inert. v2 enables it behind the
 *     `stripe_recharge_enabled` feature flag (seeded FALSE in Phase 1); the
 *     backend `WalletService.recharge(payment_provider="stripe")` raises
 *     `NotImplementedError` until then.
 *
 * Money is rendered exactly as the backend serialized it — a STRING (SC#4); we
 * never parse it to a JS number (floats would lose the NUMERIC(18,4) precision,
 * PITFALLS #4). Copy is ENGLISH and deliberately avoids the word "deposit"
 * (PITFALLS #3 — this is play money: "Add funds" / "play balance", never
 * "deposit").
 *
 * Data fetch (server-side, cookie-forwarded — mirrors `lib/auth.ts`): the page
 * reads `BACKEND_URL` from the server env (no `NEXT_PUBLIC_` prefix, so it never
 * leaks into the client bundle) and forwards the player's `xpredict_session`
 * cookie to `GET /wallet/me/balance` + `/wallet/me/transactions`. If the backend
 * is unreachable or the session is missing, it degrades to a zero balance + an
 * empty history rather than crashing (a follow-up phase can harden the redirect
 * to /login). The fetch is isolated in `loadWallet()` so tests can mock it.
 */
import { cookies } from "next/headers";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const CURRENCY = "PLAY_USD";

type TransactionItem = {
  kind: string;
  amount: string; // SC#4 — money is a JSON string, never a float.
  direction: "debit" | "credit" | string;
  created_at: string;
  reason: string | null;
};

type WalletData = {
  balance: string; // SC#4 — string.
  currency: string;
  transactions: TransactionItem[];
};

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

/**
 * Fetch the player's balance + recent history server-side, forwarding the
 * session cookie. Degrades to a zero balance / empty history on any failure so
 * the page always renders (the read endpoints are cookie-gated server-side).
 */
async function loadWallet(): Promise<WalletData> {
  const fallback: WalletData = {
    balance: "0",
    currency: CURRENCY,
    transactions: [],
  };
  try {
    const store = await cookies();
    const session = store.get("xpredict_session")?.value;
    if (!session) return fallback;

    const headers = { Cookie: `xpredict_session=${session}` };
    const base = getBackendUrl();

    const [balanceRes, txRes] = await Promise.all([
      fetch(`${base}/wallet/me/balance`, { headers, cache: "no-store" }),
      fetch(`${base}/wallet/me/transactions`, { headers, cache: "no-store" }),
    ]);

    const balance: string =
      balanceRes.ok && typeof (await balanceRes.clone().json()).balance === "string"
        ? (await balanceRes.json()).balance
        : fallback.balance;

    const transactions: TransactionItem[] = txRes.ok
      ? ((await txRes.json()).items ?? [])
      : [];

    return { balance, currency: CURRENCY, transactions };
  } catch {
    return fallback;
  }
}

export default async function WalletPage() {
  const { balance, currency, transactions } = await loadWallet();

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Wallet</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Your play balance and recent activity.
        </p>
      </header>

      {/* Balance + Add funds (SC#6 — the Add funds button is DISABLED) */}
      <Card>
        <CardHeader>
          <CardDescription>Play balance</CardDescription>
          <CardTitle>
            <span aria-label="wallet balance">{balance}</span>{" "}
            <span className="text-base font-normal text-zinc-500">
              {currency}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-start gap-2">
          {/*
            SC#6 / PLT-05: the Stripe top-up affordance is present but INERT.
            v2 enables it behind the `stripe_recharge_enabled` feature flag.
          */}
          <Button type="button" disabled aria-disabled="true">
            Add funds
          </Button>
          <p className="text-xs text-zinc-500">Coming soon</p>
        </CardContent>
      </Card>

      {/* Transaction history (WAL-04) */}
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium tracking-tight">Recent activity</h2>
        {transactions.length === 0 ? (
          <p className="text-sm text-zinc-500" data-testid="wallet-history-empty">
            No transactions yet.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
            {transactions.map((tx, i) => (
              <li
                key={`${tx.created_at}-${i}`}
                className="flex items-center justify-between py-3"
              >
                <span className="flex flex-col">
                  <span className="text-sm font-medium capitalize">
                    {tx.kind}
                  </span>
                  {tx.reason ? (
                    <span className="text-xs text-zinc-500">{tx.reason}</span>
                  ) : null}
                </span>
                <span className="flex items-center gap-2">
                  <span
                    className={
                      tx.direction === "credit"
                        ? "text-sm font-medium text-emerald-600"
                        : "text-sm font-medium text-zinc-700 dark:text-zinc-300"
                    }
                  >
                    {tx.direction === "credit" ? "+" : "-"}
                    {tx.amount} {currency}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
