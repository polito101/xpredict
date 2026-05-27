/**
 * Plan 02-04 — Shared layout for the `(auth)` route group.
 *
 * The parens in `(auth)` make Next.js skip the segment in the URL — pages
 * keep their flat paths (`/login`, `/register`, ...) while sharing this
 * centered Card wrapper.
 *
 * Server Component (no `"use client"`) — purely structural.
 */
import { Card, CardContent } from "@/components/ui/card";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950 p-6">
      <Card className="w-full max-w-md">
        <CardContent className="p-8">{children}</CardContent>
      </Card>
    </main>
  );
}
