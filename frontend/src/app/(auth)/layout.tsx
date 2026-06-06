/**
 * Plan 02-04 — Shared layout for the `(auth)` route group.
 *
 * The parens in `(auth)` make Next.js skip the segment in the URL — pages keep
 * their flat paths (`/login`, `/register`, ...) while sharing this centered
 * brand-framed wrapper. Phase 19: the obsidian canvas + the XPredict mark above
 * a glass card give the funnel real brand presence (it renders inside the root
 * layout, so the global header/footer still frame it). Server Component.
 */
import { Card, CardContent } from "@/components/ui/card";
import { LogoMark } from "@/components/brand/logo-mark";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-[78vh] flex-col items-center justify-center px-4 py-12">
      <div className="mb-7 flex flex-col items-center gap-3 text-center">
        <LogoMark className="h-12 w-12" />
        <p className="max-w-[16rem] text-sm text-muted-foreground">
          The prediction-market platform.
        </p>
      </div>
      <Card className="w-full max-w-md surface-glass">
        <CardContent className="p-8">{children}</CardContent>
      </Card>
    </main>
  );
}
