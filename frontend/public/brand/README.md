# XPrediction brand assets

## Drop the official logo here

Save the official XPrediction logo (the blue/silver "X" + central spark, on a
**transparent background**) as **exactly**:

```
frontend/public/brand/xprediction-logo.png
```

(A square PNG, ~512×512 or larger, transparent.) That single file is the product
mark used everywhere via `components/brand/logo-mark.tsx` (`LogoMark`):

- the navbar wordmark (when no white-label operator logo is set),
- the landing hero (the ecosystem-network core + the compact mobile mark),
- the auth screens,
- the admin shell.

Until the file is present, `LogoMark` falls back to the faithful vector mark
(`components/brand/x-mark.tsx`) so nothing is ever broken — the moment you add
the PNG at the path above, every surface shows the real asset, with no code change.

An SVG works too: save it as `xprediction-logo.png`'s sibling and point
`OFFICIAL_LOGO_SRC` in `logo-mark.tsx` at it (one line).

## White-label (operator) logo — separate

Operator-specific logos are NOT committed here. They are uploaded at runtime via
`/admin/branding` and served by the backend at `/branding/logo`; `BrandLogo`
renders that over the default mark in the navbar (white-label). See
`.planning/phases/phase-19-premium-experience/HANDOFF.md`.
