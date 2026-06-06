/**
 * Plan 02-04 — Email verification page.
 *
 * Client component: reads `?token=` from `useSearchParams`, then auto-calls
 * `verifyEmailAction(token)` on mount. Displays loading / success / error
 * states based on the action's return value.
 *
 * Wraps the inner client in <Suspense> because `useSearchParams()` requires
 * a suspense boundary under Next 15 (the static export pre-render path
 * otherwise raises during `next build`).
 */
"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { verifyEmailAction } from "@/lib/auth";
import type { VerifyResult } from "@/lib/auth-schemas";
import { Button } from "@/components/ui/button";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [result, setResult] = useState<VerifyResult | null>(null);
  const [pending, setPending] = useState<boolean>(true);

  useEffect(() => {
    if (!token) {
      setResult({ status: "error", detail: "Missing token in URL." });
      setPending(false);
      return;
    }
    let cancelled = false;
    (async () => {
      const r = await verifyEmailAction(token);
      if (!cancelled) {
        setResult(r);
        setPending(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="space-y-6 text-center">
      <header className="space-y-2">
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Verifying your email
        </h1>
      </header>
      {pending && (
        <p role="status" className="text-sm text-muted-foreground">
          Please wait…
        </p>
      )}
      {!pending && result?.status === "success" && (
        <>
          <p
            role="status"
            className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400"
          >
            Email verified! You can now sign in.
          </p>
          <Button asChild className="w-full">
            <Link href="/login">Sign in</Link>
          </Button>
        </>
      )}
      {!pending && result?.status === "error" && (
        <>
          <p
            role="alert"
            className="rounded-xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-400"
          >
            {result.detail ?? "We couldn't verify your email."}
          </p>
          <Button asChild variant="outline" className="w-full">
            <Link href="/login">Back to sign in</Link>
          </Button>
        </>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <p role="status" className="text-sm text-muted-foreground">
          Loading…
        </p>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
