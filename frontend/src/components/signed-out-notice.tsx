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
      className="flex flex-col items-start gap-3 rounded-2xl border border-border bg-surface p-6"
    >
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-foreground">
          Sign in to see your {resource}
        </p>
        <p className="text-sm text-muted-foreground">
          Your {resource} is private to your account.
        </p>
      </div>
      <Button asChild>
        <Link href="/login">Log in</Link>
      </Button>
    </div>
  );
}
