/**
 * ContactSection — the landing's "talk to us" band (Quality Pass).
 *
 * A clear contact apartment for sales/partnerships/demos/support: an inviting
 * copy column + a contact card with the support email (mailto) and the brand's
 * socials. Targeted by the header's `#contact` section link. Server Component
 * (composes the client SocialLinks). The email is the single source of truth in
 * SUPPORT_EMAIL so it's trivial to update.
 */
import Link from "next/link";
import { Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SocialLinks } from "@/components/social-links";

const SUPPORT_EMAIL = "support@xprediction.online";

export function ContactSection() {
  return (
    <section
      id="contact"
      className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20"
    >
      <div className="grid items-center gap-10 rounded-3xl border border-border bg-card/60 p-8 sm:p-12 lg:grid-cols-2">
        {/* Invitation */}
        <div className="flex flex-col gap-4">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
            Contact
          </span>
          <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            Talk to the team.
          </h2>
          <p className="max-w-xl text-base text-muted-foreground">
            Questions about the platform, a white-label deployment, a demo, or
            support? Reach us directly — we&apos;d love to hear what you&apos;re
            building.
          </p>
          <div className="flex flex-wrap items-center gap-4 pt-1">
            <Button asChild size="lg" className="glow-brand">
              <Link href={`mailto:${SUPPORT_EMAIL}`}>Email us</Link>
            </Button>
            <SocialLinks />
          </div>
        </div>

        {/* Contact card */}
        <div className="flex flex-col gap-4 rounded-2xl border border-border bg-surface/60 p-6 transition-colors hover:border-brand-primary/40">
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
          <p className="text-sm leading-relaxed text-muted-foreground">
            For sales, partnerships, and platform support. One inbox, straight to
            the team behind XPrediction.
          </p>
        </div>
      </div>
    </section>
  );
}
