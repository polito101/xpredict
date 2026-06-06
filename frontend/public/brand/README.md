# XPrediction brand assets

## `xprediction-logo.png` — the official product mark (committed, active)

The official XPrediction logo (the blue/silver "X" + central spark, transparent
background) lives here and is the active product mark across the app — rendered
everywhere via `components/brand/logo-mark.tsx` (`LogoMark`):

- the navbar wordmark (when no white-label operator logo is set),
- the landing hero (the ecosystem-network core + the compact mobile mark),
- the auth screens,
- the admin shell.

To update it, replace this file (keep the name + a transparent PNG). `LogoMark`
falls back to the vector mark (`components/brand/x-mark.tsx`) only if the file is
ever missing, so the UI never breaks.

## White-label (operator) logo — separate

Operator-specific logos are NOT committed here. They are uploaded at runtime via
`/admin/branding`, served by the backend at `/branding/logo`, and rendered over
the default mark in the navbar (white-label). See
`.planning/phases/phase-19-premium-experience/HANDOFF.md`.
