# XPredict — Phase 19 UI-SPEC (implementation contract)

The concrete token system, primitive restyle rules, and per-screen build plan. Tailwind v4
(CSS-first, `@theme inline`). Dark-first. White-label brand vars preserved.

---

## 1. Token system (`globals.css`)

### 1.1 Base `:root` (dark-first — the single source of truth, `color-scheme: dark`)

```
/* Brand — white-label, runtime-injected. XPredict default = electric blue / spark cyan. */
--brand-primary:            #2563EB;   /* electric royal blue (white FG via pickReadableForeground) */
--brand-primary-foreground: #f8fafc;
--brand-secondary:          #38BDF8;   /* spark cyan — gradient/glow endpoint */

/* Obsidian canvas + liquid-silver neutral ramp (cool, blue-tinted) */
--background:        #060912;   /* deep obsidian */
--surface:          #0A0F1C;   /* page sections / subtle fills */
--surface-2:        #0E1424;
--card:             #0E1424;   /* card base */
--card-foreground:  #E8ECF6;
--popover:          #131A2C;   /* dialogs, dropdowns, elevated */
--popover-foreground:#E8ECF6;
--muted:            #161D30;   /* inputs, muted fills */
--muted-foreground: #9AA6BE;   /* secondary text */
--subtle-foreground:#69748C;   /* tertiary/meta text */
--foreground:       #E8ECF6;   /* primary ink (cool near-white) */
--border:           #20293F;   /* hairline */
--border-strong:    #33405C;
--input:            #232E47;   /* input border */
--ring:             #2563EB;   /* = brand-primary */

/* Semantic (re-toned for dark; emerald/amber/red families kept) */
--success:#34D399; --success-foreground:#052E22;
--warning:#FBBF24; --warning-foreground:#3A2A05;
--danger:#F87171;  --destructive:#EF4444;  /* destructive BUTTON stays red-500 */

--radius: 0.875rem;            /* 14px base; cards 1rem */
```

### 1.2 `@theme inline` — expose every token as a utility

Map all of the above to `--color-*` (+ `--radius`, `--font-display`, `--font-sans`) so these exist:
`bg-background|surface|surface-2|card|popover|muted`, `text-foreground|card-foreground|muted-foreground|subtle-foreground|popover-foreground`,
`border-border|border-strong|input`, `ring-ring`, `bg/text/border/ring-brand-primary`, `bg-brand-secondary`,
`text/bg-success|warning|danger`. (Fixes the latent `ring-offset-background` since `--color-background` now exists.)

### 1.3 Identity utilities / keyframes (additive layer)

- `--gradient-brand: linear-gradient(135deg, var(--brand-primary), var(--brand-secondary))`
- `--gradient-metal: linear-gradient(140deg,#F4F7FF 0%,#C2CCE3 45%,#7C88A6 100%)` (liquid silver)
- Utilities (in `globals.css` `@layer utilities`): `.text-gradient-brand`, `.bg-gradient-brand`,
  `.text-metal`, `.glow-brand` (blue box-shadow), `.glow-brand-sm`, `.surface-glass` (blur + translucent
  card + hairline), `.aurora` (fixed radial obsidian backdrop).
- Keyframes: `spark-pulse`, `shimmer`, `glow-breathe`, `rise-in` (y+scale, never opacity-only).
- Shadows: `--shadow-card`, `--shadow-pop`, `--shadow-glow` (deep, slightly-blue, soft).

### 1.4 Fonts (`layout.tsx`)

`Space_Grotesk({variable:"--font-display"})` + existing `Inter({variable:"--font-sans"})`. `globals.css`:
headings/`.font-display` → `var(--font-display)`; body → `var(--font-sans)`. Big numbers use display +
`tabular-nums`.

---

## 2. Primitive restyle (the whole-app reskin — `components/ui/*`)

Base classes become tokens; remove now-redundant `dark:` pairs (base is already dark). Keep all
behavior, props, displayNames, aria, testids.

| File | New treatment |
|------|---------------|
| `card.tsx` | `bg-card text-card-foreground border-border rounded-2xl` + `--shadow-card`; optional `.surface-glass` for chrome cards. The base surface. |
| `button.tsx` | KEEP default `bg-brand-primary text-brand-primary-foreground` + `ring-brand-primary` (asserted). Add premium hover (`hover:brightness-110`, subtle `.glow-brand-sm` on default), keep `active:scale-[0.97]`. Tokenize `secondary` (`bg-muted text-foreground`), `outline` (`border-input bg-transparent hover:bg-muted`), `ghost` (`hover:bg-muted`), `link`. **destructive stays `bg-red-500`.** Unify ring → `ring-ring`. |
| `input.tsx` / `textarea.tsx` | `bg-muted border-input text-foreground placeholder:text-subtle-foreground`, focus `ring-ring`, `h-11` inputs (touch). |
| `select.tsx` | trigger like input; content `bg-popover border-border`. ring → `ring-ring`. |
| `dialog.tsx` | content `bg-popover border-border rounded-2xl` + `--shadow-pop`; overlay `bg-background/80 backdrop-blur-sm`. |
| `dropdown-menu.tsx` / `tooltip.tsx` | `bg-popover border-border text-popover-foreground`. |
| `tabs.tsx` | list `bg-muted`, active trigger `bg-card text-foreground` + subtle ring. |
| `table.tsx` | header `text-muted-foreground border-border`, row hover `bg-surface`, dividers `border-border`. |
| `badge.tsx` | default `bg-brand-primary/15 text-brand-primary border-brand-primary/30`; secondary `bg-muted text-muted-foreground border-border`; outline `border-border text-foreground`; destructive red. ring → `ring-ring`. |
| `separator.tsx` | `bg-border`. |
| `skeleton.tsx` | `bg-muted` shimmer (use `shimmer` keyframe over `animate-pulse` for premium). |
| `sonner.tsx` | toast `bg-popover border-border text-foreground`; keep `theme` wiring. |
| `label.tsx` / `form.tsx` | classes only; error → `text-danger`, description → `text-muted-foreground`. |

---

## 3. Identity components (new — `components/brand/*`)

- `XMark` (`x-mark.tsx`) — the official angular-X SVG (blue + silver gradient arms + 4-point central
  spark), themable via `currentColor`/brand vars, sizes via className. The DEFAULT logo mark.
- `Spark` (`spark.tsx`) — the 4-point lens-flare (animated, reduced-motion-safe). Reused on hero, live
  pulse, placed/won.
- `Aurora` (`aurora.tsx`) — fixed obsidian radial backdrop (brand-tinted glows at the X crossing).
- `public/brand/xpredict-mark.svg` + `xpredict-logo.svg` (wordmark lockup) + favicon — the default
  asset that `BrandLogo` falls back to (operator upload still overrides via `/branding/logo`).

`BrandLogo`: when `logoUrl` is null, render `XMark` (+ wordmark) instead of the bare dot; keep zinc-safe
ink rule and the `<img src=/branding/logo>` path when a logo IS set.

---

## 4. Per-screen build plan

1. **globals.css + fonts + identity primitives + default-brand change + lockstep tests** (foundation).
2. **ui/* primitives** (whole-app reskin).
3. **Chrome:** `layout.tsx` (sticky dark-glass header, `Aurora` backdrop, refined footer), `player-nav`
   (premium pill nav + mobile menu + account affordance from `/auth/users/me` display_name), `brand-logo`,
   admin `layout`/`nav` (dark-first, brand-aware, normalized H1s).
4. **Home `/`:** `HeroBand` (X + spark + gradient headline + value prop + CTA), trending rail, premium
   `MarketCard` + `EventCard` (glass, energetic gradient/glow odds bars, volume/source emphasis, lift),
   `CatalogControls` polish + mobile, skeleton parity (incl. event-card skeleton).
5. **Market detail:** oversized animated probability hero (`MarketDetailLiveOdds`/`OddsDisplay` elevated),
   premium dark `PriceHistoryChart` (gradient area fill, glow line, dark axes, custom tooltip, 24h-change
   badge), confident bet ticket, mobile sticky bet bar, `BetConfirmDialog` + `BetPlacedSuccess` spark beat,
   celebratory `MarketResolutionPanel` won state. Surface `source_url` provenance + `volume_24hr`.
6. **Event detail:** ranked `OutcomeRow` pills (leader highlighted, own YES bar), smooth panel swap,
   keep single-socket cap.
7. **Portfolio:** summary stat hero (derived from payload strings), Open/Settled tabs, enriched position
   cards (best-effort market title/link via catalog map; graceful fallback), gamified empty states.
8. **Wallet:** big-number balance hero (brand glass), dated + iconified + humanized transaction rows,
   inert Add-funds explained.
9. **Auth:** split-screen brand panel + form; show/hide password; strength meter (register/reset). Keep
   all form logic/aria/testids/copy.
10. **System:** `not-found`, `global-error` (token surfaces, no hardcoded white), `loading` skeletons.
11. **Admin polish:** shell + branding showcase via the restyled primitives.
12. **Tests + lint + typecheck + `next build --webpack` + PR + CI + MERGE READY.**

---

## 5. Verification gates (each wave)

`pnpm lint` · `pnpm typecheck` · `pnpm vitest run` (all work on Windows) after each major wave; full
`next build --webpack` before the PR (Turbopack-on-Windows caveat). Keep the DOM contract intact so the
Tier-A test bulk stays green; update the few Tier-B className tests in lockstep.
