# Regulatory posture — SKELETON + counsel-review notes

> **SCAFFOLD ONLY — NOT LEGAL ADVICE.** This document is a structural skeleton plus
> bracketed review notes. It contains **no authored, finished, or binding legal prose**.
> Every substantive legal claim below is a bracketed `[COUNSEL REVIEW REQUIRED: …]` or
> `[DEFERRED: external counsel]` note. **Counsel review** (Spanish legal counsel) of the ToS
> and token policy is a **gating external dependency** that this phase does not close.

## Regulatory posture (v1: play-money, production-grade)

XPredict v1 ships as a **play-money** product. The structural facts that keep it outside the
scope of regulated gambling are listed under "What keeps us safe" below; the legal
*characterization* of those facts is deferred to counsel.

- `[COUNSEL REVIEW REQUIRED: confirm the v1 play-money posture under Spain Ley 13/2011 and the EU general principle.]`
- `[DEFERRED: external counsel — sign-off on whether the structural facts below are sufficient to keep v1 out of the regulated-gambling definition.]`

## The three-element test (Spain Ley 13/2011)

Gambling under Spanish law generally requires **all three** elements. (See
`.planning/research/PITFALLS.md` §"The Regulatory Line" for the source analysis — referenced,
not re-authored here.)

1. **Prize** — something of economic value won.
2. **Chance** — an outcome dependent on chance.
3. **Consideration** — the player risks something of value.

- **v1 removes element 1 (no economic-value prize) and element 3 (no consideration paid).**
- `[COUNSEL REVIEW REQUIRED: confirm that removing elements 1 and 3 is the correct and sufficient defense; do not rely on this note as legal opinion.]`

## What keeps us safe

Structural facts already true in code (these are engineering facts, not legal conclusions):

- Tokens are **system-granted only** (signup bonus, daily reward, admin grant). Users never *pay*
  for tokens.
- Tokens are **non-transferable** between users — a hard constraint at the **DB level** (per WAL-09).
- Tokens are **non-redeemable** — there is no path to fiat, crypto, gift cards, swag, or prizes.
- There is **no monetary-prize leaderboard**.

- `[COUNSEL REVIEW REQUIRED: confirm these structural facts are the load-bearing safe-harbor facts and that none are mischaracterized.]`

## What breaks us — do-not-do list

A change that adds **prize** (element 1) or **consideration** (element 3) would push the product
into regulated gambling.

- See the full "What breaks us" table in `.planning/research/PITFALLS.md` §"The Regulatory Line"
  (pointer, not a re-transcription).
- `[COUNSEL REVIEW REQUIRED: confirm the do-not-do list is complete for the target jurisdictions.]`

## Geo-fencing

- `[COUNSEL REVIEW REQUIRED: jurisdiction allowlist — define the geo-block list (default-block US
  states with hostile rulings; expand the allowlist only with legal review).]`
- `[DEFERRED: external counsel — final geo-block list before any operator demo.]`

## Open counsel-review items

Checklist of what Spanish counsel must sign off **before any operator demo**. None of these is
closed by this phase.

- [ ] Terms of Service (`docs/terms-of-service.md`) — `[DEFERRED: external counsel]`
- [ ] Token policy / no-monetary-value characterization — `[DEFERRED: external counsel]`
- [ ] Geo-block list — `[DEFERRED: external counsel]`
- [ ] Operator agreement (`docs/operator-agreement.md`) finalization — `[DEFERRED: external counsel]`

> **Counsel review** of the ToS and token policy remains a **gating external dependency** on
> Phase 11 completion. It is recorded here as deferred — **not** closed, and **not** substituted
> with authored legal text.
