/**
 * Plan 03-05 Task 3 — Player wallet page (WAL-03 balance, WAL-04 history, SC#6 stub).
 *
 * A Server Component that shows the logged-in player their play balance, recent
 * transaction history, and a DISABLED "Add funds" button (SC#6 / PLT-05 — the
 * Stripe top-up affordance is present but inert until v2).
 *
 * Money is rendered exactly as the backend serialized it — a STRING (SC#4); we
 * never parse it to a JS number (floats would lose NUMERIC(18,4) precision,
 * PITFALLS #4). Copy is ENGLISH and avoids "deposit" (PITFALLS #3 — play money).
 *
 * Failure handling (v1.1 Fase C): the fetch result is a discriminated union, so
 * the page distinguishes three cases instead of silently degrading every one to
 * a misleading "0":
 *   - `unauthenticated` (no session cookie) → a sign-in prompt,
 *   - `error` (backend unreachable / non-2xx) → a non-silent RetryError, and
 *   - `ok` → the balance + history (with an empty state when there's none).
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
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";

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

type WalletResult =
  | { status: "ok"; data: WalletData }
  | { status: "error" }
  | { status: "unauthenticated" };

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

/**
 * Fetch the player's balance + recent history server-side, forwarding the
 * session cookie. Returns a discriminated result so the page can tell apart a
 * signed-out visitor, a backend failure, and a genuinely empty wallet.
 */
async function loadWallet(): Promise<WalletResult> {
  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
  if (!session) return { status: "unauthenticated" };

  try {
    const headers = { Cookie: `xpredict_session=${session}` };
    const base = getBackendUrl();

    const [balanceRes, txRes] = await Promise.all([
      fetch(`${base}/wallet/me/balance`, { headers, cache: "no-store" }),
      fetch(`${base}/wallet/me/transactions`, { headers, cache: "no-store" }),
    ]);

    if (!balanceRes.ok || !txRes.ok) return { status: "error" };

    const balanceJson = (await balanceRes.json()) as { balance?: unknown };
    const txJson = (await txRes.json()) as { items?: TransactionItem[] };
    const balance =
      typeof balanceJson.balance === "string" ? balanceJson.balance : "0";

    return {
      status: "ok",
      data: { balance, currency: CURRENCY, transactions: txJson.items ?? [] },
    };
  } catch {
    return { status: "error" };
  }
}

export default async function WalletPage() {
  const result = await loadWallet();

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-12 sm:px-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Wallet</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Your play balance and recent activity.
        </p>
      </header>

      {result.status === "unauthenticated" ? (
        <SignedOutNotice resource="wallet" />
      ) : result.status === "error" ? (
        <RetryError
          title="We couldn't load your wallet"
          message="The balance service didn't respond. Your funds are safe — please try again."
        />
      ) : (
        <WalletContent {...result.data} />
      )}
    </main>
  );
}

function WalletContent({ balance, currency, transactions }: WalletData) {
  return (
    <>
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
                className="flex items-center justify-between gap-3 py-3"
              >
                <span className="flex min-w-0 flex-col">
                  <span className="text-sm font-medium capitalize">
                    {tx.kind}
                  </span>
                  {tx.reason ? (
                    <span className="truncate text-xs text-zinc-500">
                      {tx.reason}
                    </span>
                  ) : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span
                    className={
                      tx.direction === "credit"
                        ? "whitespace-nowrap text-sm font-medium text-emerald-600"
                        : "whitespace-nowrap text-sm font-medium text-zinc-700 dark:text-zinc-300"
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
    </>
  );
}
