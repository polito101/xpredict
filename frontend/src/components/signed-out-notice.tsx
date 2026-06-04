/**
 * SignedOutNotice — shown on a private player surface (wallet, portfolio) when
 * there is no session, instead of rendering a misleading empty/zero state to a
 * signed-out visitor (v1.1 Fase C).
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";

export function SignedOutNotice({ resource }: { resource: string }) {
  return (
    <div
      role="status"
      className="flex flex-col items-start gap-3 rounded-lg border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-900/40"
    >
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Sign in to see your {resource}
        </p>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Your {resource} is private to your account.
        </p>
      </div>
      <Button asChild>
        <Link href="/login">Log in</Link>
      </Button>
    </div>
  );
}
