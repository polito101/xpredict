import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * Global 404 (v1.1 Fase C). Rendered inside the player root layout, so it keeps
 * the header-nav / footer / branding — only the body is the not-found notice.
 */
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] w-full max-w-md flex-col items-center justify-center gap-4 px-4 py-16 text-center">
      <p className="text-sm font-semibold uppercase tracking-wide text-brand-primary">
        404
      </p>
      <h1 className="text-3xl font-semibold tracking-tight">Page not found</h1>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        The page you&apos;re looking for doesn&apos;t exist or may have moved.
      </p>
      <Button asChild>
        <Link href="/">Back to markets</Link>
      </Button>
    </main>
  );
}
