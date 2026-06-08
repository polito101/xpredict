/**
 * ContactSection — "Get a demo / talk to the team" (infra-company refinement).
 *
 * Elevated from a plain contact card into a serious commercial conversation: it
 * frames the kinds of engagements (live demo, white-label deployment, partnerships,
 * technical deep-dive) and surfaces the support email as the channel. Targeted by
 * the header's `#contact` link. Server Component (composes client SocialLinks).
 * The email is the single source of truth in SUPPORT_EMAIL.
 */
import Link from "next/link";
import { Mail, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SocialLinks } from "@/components/social-links";

const SUPPORT_EMAIL = "support@xprediction.online";

/** What a conversation with the team actually covers. */
const TOPICS = [
  "Live product demo",
  "White-label deployment",
  "Platform partnerships & integrations",
  "Technical deep-dive",
] as const;

export function ContactSection() {
  return (
    <section
      id="contact"
      className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20"
    >
      <div className="grid items-start gap-10 rounded-3xl border border-border bg-card/60 p-8 sm:p-12 lg:grid-cols-2">
        {/* Invitation */}
        <div className="flex flex-col gap-4">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
            Get a demo
          </span>
          <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            Let&apos;s get your markets live.
          </h2>
          <p className="max-w-xl text-base text-muted-foreground">
            Walk through the platform with the team, plan a white-label
            deployment, or talk partnerships and integrations — straight from the
            people who build it.
          </p>
          <div className="flex flex-wrap items-center gap-4 pt-1">
            <Button asChild size="lg" className="glow-brand">
              <Link
                href={`mailto:${SUPPORT_EMAIL}?subject=XPrediction%20demo%20request`}
              >
                Request a demo
              </Link>
            </Button>
            <SocialLinks />
          </div>
        </div>

        {/* What the conversation covers + the channel */}
        <div className="flex flex-col gap-5 rounded-2xl border border-border bg-surface/60 p-6">
          <ul className="flex flex-col gap-3">
            {TOPICS.map((t) => (
              <li
                key={t}
                className="flex items-center gap-3 text-sm text-foreground"
              >
                <Check
                  className="h-4 w-4 shrink-0 text-brand-primary"
                  aria-hidden="true"
                  strokeWidth={2.5}
                />
                {t}
              </li>
            ))}
          </ul>

          <div className="h-px bg-border" aria-hidden="true" />

          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-brand-primary/25 bg-brand-primary/10 text-brand-primary">
              <Mail className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wide text-subtle-foreground">
                Email
              </p>
              <Link
                href={`mailto:${SUPPORT_EMAIL}`}
                className="break-all font-medium text-foreground transition-colors hover:text-brand-primary"
              >
                {SUPPORT_EMAIL}
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
