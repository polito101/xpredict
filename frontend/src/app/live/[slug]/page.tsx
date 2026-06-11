/**
 * `/live/[slug]` — fullscreen widget host for ONE catalog table (live
 * multi-table plan). Resolves the slug against `LIVEBETS_TABLES`
 * (`findLiveTable`), mints the live-bets session FOR THAT TABLE
 * (`fetchLiveSession(session, tableId)` → LB-A `POST /api/live/session`
 * `{table_id}`), and renders the Plan D fullscreen overlay with the catalog
 * label as the widget HUD `counter-label`.
 *
 * States (mirrors /live):
 *   - unknown slug          → notFound() (404).
 *   - no session cookie     → SignedOutNotice.
 *   - mint failure          → non-silent RetryError (an explicit-table 400 is a
 *     misconfigured catalog, NOT the friendly unconfigured empty state).
 *   - balance read failure  → non-silent RetryError (no fake "0").
 *   - success               → full-viewport overlay (widget HUD owns all UI).
 */
import { Suspense } from "react";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { fetchLiveSession } from "@/lib/api";
import { findLiveTable } from "@/lib/live-catalog";
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";
import {
  LiveFullscreenHost,
  LiveShell,
  LiveSkeleton,
  loadBalance,
  PAGE_SHELL,
} from "../shared";

async function LiveSlugBody({ slug }: { slug: string }) {
  const entry = findLiveTable(slug);
  if (!entry) notFound();

  // Auth gate: cookie presence only — the value never crosses into client JS.
  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
  if (!session) {
    return (
      <main className={PAGE_SHELL}>
        <header className="mb-8 flex flex-col gap-1">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            {entry.label}
          </h1>
          <p className="text-sm text-muted-foreground">
            Multiplayer live bets with your XPrediction balance.
          </p>
        </header>
        <SignedOutNotice resource="live" />
      </main>
    );
  }

  // SP-5: mint for THIS table + read the balance in parallel.
  const [sessionResult, balanceResult] = await Promise.allSettled([
    fetchLiveSession(session, entry.tableId),
    loadBalance(session),
  ]);

  const balance =
    balanceResult.status === "fulfilled" && balanceResult.value.ok
      ? balanceResult.value.balance
      : null;

  // Any mint failure here (including a 400 on an explicit table_id — that is a
  // misconfigured catalog, not the LB-B "unconfigured" demo state) → retry error.
  if (sessionResult.status === "rejected") {
    return (
      <LiveShell>
        <RetryError
          title="We couldn't load the live table"
          message="The live-bets service didn't respond. Please try again."
        />
      </LiveShell>
    );
  }

  if (balance === null) {
    return (
      <LiveShell>
        <RetryError
          title="We couldn't load your balance"
          message="The balance service didn't respond. Your funds are safe — please try again."
        />
      </LiveShell>
    );
  }

  const { session_token, table_id } = sessionResult.value;
  return (
    <LiveFullscreenHost
      sessionToken={session_token}
      tableId={table_id}
      initialBalance={balance}
      counterLabel={entry.label}
    />
  );
}

export default async function LiveSlugPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <Suspense fallback={<LiveSkeleton />}>
      <LiveSlugBody slug={slug} />
    </Suspense>
  );
}
