/**
 * ApiSection — the developer / API-first story (Phase 19 landing).
 *
 * Reinforces the platform positioning with the real integration surface: a
 * typed REST + WebSocket API over a double-entry ledger. The capability checks
 * and the sample request/response use REAL endpoint shapes from the backend (no
 * over-claiming). Server Component.
 */
import { Check } from "lucide-react";

const FEATURES = [
  "REST + JSON API",
  "Real-time odds over WebSocket",
  "Double-entry ledger settlement",
  "Separate player & admin auth, secure by default",
  "One-command Docker deploy — production-ready",
] as const;

export function ApiSection() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
      <div className="grid items-center gap-10 lg:grid-cols-2">
        {/* Copy + checks */}
        <div className="flex flex-col gap-6">
          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
              Developer-first
            </span>
            <h2 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
              An API for the whole lifecycle.
            </h2>
            <p className="mt-3 text-base text-muted-foreground">
              Catalog, markets, wallets, bets, settlement and branding — typed
              endpoints designed to drop into your product.
            </p>
          </div>
          <ul className="flex flex-col gap-3">
            {FEATURES.map((f) => (
              <li key={f} className="flex items-center gap-3 text-sm">
                <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand-primary/15 text-brand-primary">
                  <Check className="h-3 w-3" aria-hidden="true" />
                </span>
                <span className="text-foreground">{f}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Code card */}
        <div className="overflow-hidden rounded-2xl border border-border bg-[#070b16] shadow-pop">
          <div className="flex items-center gap-1.5 border-b border-border px-4 py-3">
            <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
            <span className="ml-2 text-xs text-subtle-foreground">
              GET /api/v1/catalog
            </span>
          </div>
          <pre className="overflow-x-auto p-4 font-mono text-[0.78rem] leading-relaxed">
            <code>
              <span className="text-subtle-foreground">{"// public catalog — markets + multi-outcome events\n"}</span>
              <span className="text-emerald-400">{"curl"}</span>
              <span className="text-foreground/90">{' https://api.xpredict.app/api/v1/catalog\n\n'}</span>
              <span className="text-foreground/90">{"[\n  {\n    "}</span>
              <span className="text-brand-primary">{'"type"'}</span>
              <span className="text-foreground/90">{": "}</span>
              <span className="text-emerald-400">{'"event"'}</span>
              <span className="text-foreground/90">{",\n    "}</span>
              <span className="text-brand-primary">{'"title"'}</span>
              <span className="text-foreground/90">{": "}</span>
              <span className="text-emerald-400">{'"Who wins the final?"'}</span>
              <span className="text-foreground/90">{",\n    "}</span>
              <span className="text-brand-primary">{'"volume"'}</span>
              <span className="text-foreground/90">{": "}</span>
              <span className="text-emerald-400">{'"48250.0000"'}</span>
              <span className="text-foreground/90">{",\n    "}</span>
              <span className="text-brand-primary">{'"outcomes"'}</span>
              <span className="text-foreground/90">{": [\n      { "}</span>
              <span className="text-brand-primary">{'"label"'}</span>
              <span className="text-foreground/90">{": "}</span>
              <span className="text-emerald-400">{'"Alice"'}</span>
              <span className="text-foreground/90">{", "}</span>
              <span className="text-brand-primary">{'"yes_price"'}</span>
              <span className="text-foreground/90">{": "}</span>
              <span className="text-emerald-400">{'"0.62"'}</span>
              <span className="text-foreground/90">{" }\n    ]\n  }\n]"}</span>
            </code>
          </pre>
        </div>
      </div>
    </section>
  );
}
