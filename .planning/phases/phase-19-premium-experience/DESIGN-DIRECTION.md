# XPredict — Phase 19 Premium Experience: Design Direction

> A dark-first, premium reimagining of the XPredict web experience, built natively around the
> official logo. Frontend-only: every screen wires to the **existing** backend + backoffice; the
> white-label runtime branding system is preserved. No domain/API changes.

---

## 1. The logo, read as a design language

The official mark is a sharp, beveled **"X"** on near-black:

- **Two electric royal-blue arms** (deep blue body → bright blue highlights) crossed with **two
  liquid-silver/white arms** (cool metallic gradient). The duotone — *electric blue × liquid silver*
  — is the core palette.
- A **brilliant 4-point star / lens-flare at the crossing center** (white-blue core, horizontal +
  vertical light streaks). This is the signature: **the spark** — the instant where opinions cross
  and a prediction is made. It is the emotional center of the brand.
- **Obsidian canvas** with a subtle blue undertone and a soft radial vignette around the crossing.
- Crisp inner angles, softly rounded outer corners — *precise, but not cold.*

**Personality extracted:** precise · confident · kinetic · premium · a touch of sci-fi/fintech.
Reference altitude: Linear's craft × a premium trading terminal × Polymarket's domain — but warmer,
more cinematic, and unmistakably *ours*.

**The one-line test (the goal):** a single screenshot — obsidian surface, an electric-blue/silver
gesture, a spark at a crossing point — should read as **XPredict** before any wordmark is seen.

---

## 2. Identity system: "Obsidian & Spark"

| Pillar | Decision |
|--------|----------|
| **Canvas** | Deep obsidian with a blue undertone (`#060912`), layered surfaces, soft radial "aurora" glows that echo the X crossing. Dark-first, no light mode (matches the existing no-toggle decision). |
| **Energy** | Electric royal blue (`--brand-primary`, default `#2563EB`) for action, odds, focus, live state. Used as solid accents AND as a blue→cyan gradient ("the spark gradient") for hero moments, glows, and the YES odds fill. |
| **Chrome** | Liquid-silver neutral ramp — a *cool, blue-tinted* grey scale (not warm zinc) so ink/surfaces feel like brushed metal on obsidian. |
| **The spark** | A reusable 4-point lens-flare motif (`<Spark/>`): on the logo, at the hero crossing, on the live pulse, on a placed/won bet. The brand's recurring "moment". |
| **Type** | **Space Grotesk** (display/headings/big-numbers — geometric, echoes the angular X) + **Inter** (body, already wired). Tabular figures for all money/odds. |
| **Depth** | Real elevation vocabulary: layered surfaces, hairline cool borders, soft deep shadows, selective brand glow, and restrained glass on the chrome. Replaces the current flat `shadow-sm`. |
| **Motion** | Purposeful, fast, reduced-motion-safe: spark shimmer, odds-bar fill/glow, card lift, hero parallax-lite, a celebratory placed/won beat. Never gratuitous. |

**Accent discipline (white-label safe):** the electric blue is the *default tenant palette*, injected
through the untouched `--brand-primary` / `--brand-secondary` pipeline. Operators still re-skin live.
The obsidian + silver neutral system is brand-independent, so any tenant color looks intentional on it.

---

## 3. UX direction

- **Mobile-first, desktop-premium.** Every screen designed for thumb reach first; desktop earns
  extra cinema (hero bands, split-screens, sticky rails). Fix the current gaps: no mobile nav, the
  bet CTA buried below the fold on phones, horizontal-scroll filters with no affordance.
- **Make the data the hero.** The probability and the balance are the two most-looked-at numbers in
  a prediction product and today they're tiny. Oversized, animated, semantically colored.
- **One confident path per screen.** A clear primary action (browse → bet, log in, place bet,
  recharge intent). Secondary noise demoted.
- **Trust is a feature.** Keep the always-visible resolution criteria, the anonymized activity feed,
  the play-money disclaimer, the loss-is-neutral rule — but present them with craft, not as fine print.
- **Celebrate the moments.** Placing a bet and winning should *feel* like something (the spark).
- **Accessibility is non-negotiable.** Preserve every `role`/`aria`/testid/contrast guardrail from the
  audit; ≥44px targets; reduced-motion; legible-foreground derivation intact.

---

## 4. Screen architecture (information hierarchy)

| Screen | Hero moment | Primary action |
|--------|-------------|----------------|
| **Home `/`** | Obsidian hero band: the X + spark, electric gradient headline, value prop, live "trending" rail; then the dual-card catalog grid (markets + events) with energetic odds bars. | Find a market → tap a card |
| **Market `/markets/[slug]`** | Oversized animated probability readout (YES/NO semantic color) + premium dark area chart (gradient fill, glow line, 24h-change badge) over the trust column; confident sticky bet ticket; celebratory resolved/won state. | Place a bet |
| **Event `/events/[slug]`** | Ranked, color-cued outcome rows (leader highlighted) each an independent YES bar (framing LOCK); the single-socket sticky ticket panel with smooth swap. | Pick an outcome → bet |
| **Auth `/login`,`/register`,…** | Split-screen: left obsidian brand panel (X + spark + one-line value prop + play-money trust line); right the form on a refined dark surface (+ show/hide, strength meter). | Sign in / Create account |
| **Portfolio `/portfolio`** | Dashboard header: total staked · open P&L · realized P&L · win-rate · # positions; Open/Settled tabs; per-position cards that name + link the market (best-effort enrichment), result color-cued. | See performance → revisit a market |
| **Wallet `/wallet`** | Big-number balance hero in brand-framed glass; iconified, **dated** transaction rows with humanized kinds. | (Add funds — kept inert, v2) |
| **Admin `/admin/*`** | Dark-first, brand-aware shell; the design system flows in via the shared primitives; the **branding page** is the showcase. | Operate the platform |
| **System (404 / error / loading)** | On-brand obsidian, no hardcoded white; skeleton parity. | Recover |

---

## 5. Hard constraints honored (from the audit — the "do not break" set)

- **White-label pipeline:** `--brand-primary` / `--brand-primary-foreground` / `--brand-secondary`
  stay on `:root`; `@theme inline` mapping + `bg/text/border/ring-brand-primary` + `bg-brand-secondary`
  utility names preserved; `GET /branding/current` (4 fields) + `GET /branding/logo` + `fetchBrandingPublic`
  `cache:"no-store"` + the `<style>` injection (only validated hexes + `pickReadableForeground`) +
  `<img src=/branding/logo>` in `BrandLogo`, all untouched. The new "X" is the **default** mark only.
- **Default Button** keeps `bg-brand-primary` + `text-brand-primary-foreground`; **destructive** keeps
  `bg-red-500` (never brand). Focus ring unifies on the brand ring.
- **Money/odds are strings** end-to-end; round for display only.
- **Framing LOCK:** multi-outcome bars stay independent per-outcome YES% (never a stacked 100% bar).
  Preserve aria-label formats: `"YES {x}%, NO {y}%"`, `"{label}, {pct}% YES"` (button),
  `"{label}: {pct}% YES"` (bar), `"Status: {STATUS}"`.
- **Single live-socket cap** on the event page; **escaped** justification (no `dangerouslySetInnerHTML`);
  **anonymized** activity feed; session cookie never crosses to client.
- **A-LOSS-NEUTRAL:** a losing P&L renders neutral, never red.
- **Bet two-step:** submit opens `BetConfirmDialog`; only Confirm fires `placeBetAction`.
- **No layout shift:** skeletons stay dimensionally synced.
- **Toolchain:** pnpm 9.15.0 only; verify build locally with `next build --webpack`, trust Linux CI
  Turbopack; keep the `react-is` pin; don't touch Sentry wiring.

## 6. Lockstep test updates (className/style assertions that the reskin changes)

- `lib/branding-public.test.ts` — default palette indigo/sky → electric blue/cyan (update in same PR).
- `components/admin/market-status-badge.test.tsx` — status chip palette re-toned for dark.
- `components/__tests__/market-resolution-panel.test.tsx` — LOST neutral class moves to a token (keep
  the "never red" invariant).
- Any new identity component ships with its own tests (text/role/aria style).

All other tests are text/role/aria/testid and survive the reskin unchanged.
