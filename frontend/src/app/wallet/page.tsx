/**
 * Player wallet page (WAL-03 balance, WAL-04 history, SC#6 stub) — restyled to
 * the premium dark system (Phase 19).
 *
 * A Server Component (behind auth — the edge middleware gates `/wallet`) showing
 * the play balance as a big-number hero, the transaction history (now with the
 * transaction DATE and a humanized kind + a direction icon), and a DISABLED
 * "Add funds" button (SC#6 / PLT-05 — the Stripe top-up affordance is inert).
 *
 * Money is rendered exactly as the backend serialized it — a STRING (SC#4); never
 * parsed to a JS number (PITFALLS #4). Copy is ENGLISH and avoids "deposit".
 *
 * Failure handling (v1.1 Fase C): the discriminated result distinguishes
 * unauthenticated / error / ok instead of degrading every case to a fake "0".
 */
import { cookies } from "next/headers";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";
import { formatDate } from "@/lib/admin-format";

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

/** Humanize a transaction kind enum: "bet_placed" → "Bet placed". */
function humanizeKind(kind: string): string {
  const spaced = kind.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

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
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Wallet
        </h1>
        <p className="text-sm text-muted-foreground">
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
      {/* Balance hero — the most-glanced number, in brand-framed dark glass. */}
      <div className="relative overflow-hidden rounded-3xl border border-border bg-card p-6 sm:p-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-brand-primary/15 blur-3xl"
        />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-subtle-foreground">
              Play balance
            </span>
            <div className="flex items-baseline gap-2">
              <span
                aria-label="wallet balance"
                className="font-display text-4xl font-semibold tabular-nums sm:text-5xl"
              >
                {balance}
              </span>
              <span className="text-base font-medium text-muted-foreground">
                {currency}
              </span>
            </div>
          </div>
          <div className="flex flex-col items-start gap-1.5">
            {/*
              SC#6 / PLT-05: the Stripe top-up affordance is present but INERT.
              v2 enables it behind the `stripe_recharge_enabled` feature flag.
            */}
            <Button type="button" disabled aria-disabled="true">
              Add funds
            </Button>
            <p className="text-xs text-subtle-foreground">Coming soon</p>
          </div>
        </div>
      </div>

      {/* Transaction history (WAL-04) */}
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold tracking-tight">Recent activity</h2>
        {transactions.length === 0 ? (
          <p
            className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground"
            data-testid="wallet-history-empty"
          >
            No transactions yet.
          </p>
        ) : (
          <ul className="overflow-hidden rounded-2xl border border-border">
            {transactions.map((tx, i) => {
              const isCredit = tx.direction === "credit";
              return (
                <li
                  key={`${tx.created_at}-${i}`}
                  className="flex items-center justify-between gap-3 border-b border-border bg-card px-4 py-3.5 last:border-b-0"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span
                      aria-hidden="true"
                      className={
                        isCredit
                          ? "grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-500/12 text-emerald-400"
                          : "grid h-9 w-9 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"
                      }
                    >
                      {isCredit ? (
                        <ArrowDownLeft className="h-4 w-4" />
                      ) : (
                        <ArrowUpRight className="h-4 w-4" />
                      )}
                    </span>
                    <span className="flex min-w-0 flex-col">
                      <span className="text-sm font-medium text-foreground">
                        {humanizeKind(tx.kind)}
                      </span>
                      <span className="truncate text-xs text-subtle-foreground">
                        {[tx.reason, formatDate(tx.created_at)]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                  </span>
                  <span
                    className={
                      isCredit
                        ? "shrink-0 whitespace-nowrap text-sm font-medium tabular-nums text-emerald-600"
                        : "shrink-0 whitespace-nowrap text-sm font-medium tabular-nums text-muted-foreground"
                    }
                  >
                    {isCredit ? "+" : "-"}
                    {tx.amount} {currency}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </>
  );
}
