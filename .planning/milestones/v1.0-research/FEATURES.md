# Feature Research — XPredict

**Domain:** White-label prediction market platform (B2B2C)
**Researched:** 2026-05-25
**Confidence:** HIGH (cross-verified against Polymarket, Kalshi, Manifold Markets, and industry references)

## Executive Framing

XPredict has three audiences, not one — and feature decisions must account for all three:

1. **End user (player)** — a person who browses markets, places play-money bets, watches resolutions, climbs leaderboards. They have used Polymarket, Kalshi, or a sportsbook. If XPredict feels "off" compared to those, they bounce.
2. **Operator (the buyer)** — the company licensing XPredict as white-label. They live in the admin/CRM panel. Their job is to recharge balances, create house markets, resolve outcomes, monitor activity, watch dashboards. The product is sold to *them*; the player UX is what they show off to *their* users.
3. **The platform itself** — auth, audit, branding, compliance hooks. Plumbing that neither audience sees directly but breaks the sale if it looks unprofessional.

The hardest design constraint: **play money must look and feel real**. A demo that says "imaginary points!" everywhere fails the sales pitch. The visual language, transaction model, audit trail, and resolution flow should be indistinguishable from a real-money platform — only the money source is virtual. (See "Trust Signals" section.)

## Feature Landscape

### Table Stakes — End-User UI

Missing any of these will make the player feel the product is broken or unfinished. Polymarket / Kalshi / Manifold all ship these.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Market list / browse (home) | Every reference product has this; it's the front door | S | Top-25 from Polymarket + house markets, sorted by volume/recency. Cards show question, current odds, deadline, volume. |
| Market detail page | Players need a place to study before betting | M | Question, full description, resolution criteria (linked to source), price chart (history), order entry, recent activity, comments (optional). |
| Real-time price/odds updates | Polymarket/Kalshi/Manifold all push live. Stale prices = "broken" | M | WebSocket or SSE from backend. Polling-only ages the UX immediately. Industry reference: "stalls for 3 seconds = product feels broken." |
| Buy YES / Buy NO order entry | Core transaction. All binary markets work this way | M | Stake input, expected payout shown, slippage warning if needed, confirm step. Should be ≤3 taps from market detail. |
| Position / portfolio page | Players need to see "what do I own and what is it worth right now" | M | Open positions (market, side, qty, avg price, current value, unrealized P&L), settled positions, total P&L, balance. |
| Wallet / balance display | Always-visible "how much can I bet" | S | Header chip showing balance. Should never be more than 1 click away from history/recharge request. |
| Transaction history | Players must be able to audit every credit/debit on their account | S | Chronological list: deposits (admin recharge), bets placed, bets settled, payouts. Filterable by type/date. |
| Bet confirmation + receipt | After-action feedback. Reduces "did it go through?" anxiety | S | Modal/toast with "you bought X shares of YES at Y, max payout Z" + link to position. |
| Resolution display | Players need to see how a market resolved and why | S | Resolved markets show outcome, source (Polymarket UMA / admin), settle timestamp, their payout if they had a position. |
| Auth flow: register / login / logout / password reset | Production-grade requirement. Anything weaker = unprofessional | M | Email + password (Argon2), email verification, password reset via email. Persistent sessions with refresh tokens. |
| Responsive mobile web | 87% of online betting turnover is mobile (industry source) | M | Tailwind responsive breakpoints. Thumb-friendly bet entry. Not a native app — explicitly out of scope per PROJECT.md. |
| Empty / loading / error states | The difference between "polished" and "amateur" | S | Skeleton loaders, friendly empty states ("No markets yet — check back soon"), explicit error messages. |

### Table Stakes — Operator / Admin / CRM

The operator is the *buyer*. These features are what they evaluate during the sales demo. Missing any of these = the operator can't run their business.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Admin login (separate role/route) | Admins must not share the player login surface | S | `/admin` route, admin role on user model, server-side guard. Optional: admin subdomain. |
| User list / search | Operator needs to find and inspect any user | S | Paginated table: email, signup date, balance, total bet, last activity. Search by email/id. |
| User detail view | Drill-down on a single user | M | Profile, balance, transaction history, bet history, status (active/banned), notes field for operator. |
| Recharge balance (manual deposit) | Play-money model means admin tops up users on request | S | Form: pick user, amount, reason (free text), confirm. Creates an audit-logged ledger entry. |
| Ban / unban / freeze user | Operator must be able to stop abuse | S | State machine: active → suspended → banned. Suspended users can read but not bet. Audit-logged. |
| House market creation | Operator's main creative tool — define a question, options, deadline | M | Form: title, description, YES/NO or multi-choice, deadline, optional initial liquidity / opening odds, resolution criteria text. |
| House market resolution (manual) | Operator decides the outcome on house markets | M | UI: pick market in "awaiting resolution," choose winning outcome, free-text justification, confirm. Triggers automatic settlement of all positions. |
| Market list (admin view) | Operator needs to see all markets across all sources | S | Table with filter by source (Polymarket / house), status (open / closed / resolved / disputed), volume, deadline. |
| Mirrored Polymarket markets read-only | Operator should NOT be able to manually resolve a mirrored market (the oracle does that) | S | Visually distinct, "Synced from Polymarket" badge, no "Resolve" button. |
| Audit log viewer | Compliance & debugging. Every state change is reviewable | M | Immutable append-only log. Filter by entity (user, market, transaction), actor (admin, system, user), action type. Read-only — no editing. |
| Basic KPI dashboard | Operator wants 5-second pulse: "is the platform alive and healthy?" | M | Cards: total volume bet (today/week), DAU/MAU, active markets, house P&L (virtual), pending resolutions count, new signups. |
| Force-settle / manual override on stuck markets | Emergency button when oracle fails or market needs intervention | M | Logged with operator id + justification. Two-step confirm. Must be obviously logged so abuse is traceable. |
| Export to CSV (users, transactions, bets) | Operators need data for their own reports / accounting | S | Download endpoint with filters. CSV format. Industry-standard expectation. |

### Table Stakes — Platform / Infrastructure

Cross-cutting features that aren't tied to one screen. If broken, the whole product is broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Production-grade auth (Argon2 + JWT/sessions) | Anything weaker = "this isn't a real product" | M | FastAPI-users or equivalent. Hashed passwords, secure session storage, CSRF protection, rate-limit on login/register. |
| Double-entry ledger for wallets | Industry-standard accounting; "every event = debit + credit, balances must always sum to zero" | L | Two-table model (accounts + entries) or single entries table. Atomic transactions. Idempotency keys. Source of truth for *all* balances — never read from a "balance" column directly. |
| Immutable audit log | Operator + future regulator need a tamper-evident trail of every meaningful action | M | Append-only table, hash-chain optional v2. Logs: who, when, what entity, what action, before/after state. |
| ACID transactions on bet placement & settlement | A bet that debits the wallet but doesn't create a position = corruption | M | Postgres transaction wrapping wallet debit + position insert + audit log entry. Pessimistic lock on user balance row. |
| Rate limiting (login, register, bet, API) | Bot abuse protection, expected production hardening | S | Redis token-bucket per IP + per user_id. Stricter on auth endpoints. |
| Configurable branding (logo, palette) | White-label demand. Per PROJECT.md: "semilla para multi-tenant v2" | S | Env vars or single-row settings table for v1: logo url, primary color, accent color, brand name. Loaded into Next.js theme. |
| Polymarket Gamma API integration (poll + sync) | The catalog backbone | M | Celery worker polls every N seconds, upserts markets, updates odds, detects resolution events, triggers settlement of mirrored markets. |
| Email transactional (verify, password reset) | Per PROJECT.md: "emails básicos sí" | S | SMTP via SendGrid/Mailgun/Resend, templated, queued via Celery. No marketing emails (explicit anti-feature). |
| Health endpoints / observability basics | Operator needs to see "is it up?" via monitoring | S | `/health` (liveness), `/ready` (readiness checks DB/Redis/Gamma API), structured JSON logs. |
| Schema-level tenant_id field (ghost column) | Per PROJECT.md: prep for multi-tenant v2 without paying full cost now | S | All player-owned + market entities have `tenant_id` column with a single hard-coded "default" tenant value. No enforcement yet. Refactor in v2 is trivial. |

### Differentiators — End-User (Where We Compete)

These are not strictly required, but they're how XPredict turns a demo from "yeah, looks like Polymarket" into "ooh, that's clever."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Global leaderboard | Manifold-style. Turns play money into status game. Critical when there's no real money | M | Ranked by total P&L (all-time + weekly). Top 10 visible publicly. Drives engagement. |
| Brier score / calibration rating per user | Manifold's signature feature. Shows "this user predicts at 73% accuracy when they say 73%" | L | Compute on resolved positions. Display as % on profile. Sophisticated forecasters love this; novices learn from it. Defer to v1.5 if scope is tight. |
| Activity feed on market detail | Live "User X bought 100 YES at $0.42" stream. Makes market feel alive | M | Last N trades, anonymized usernames or short handles. Pushed via same WebSocket as price updates. |
| Probability history chart | Visualizes "this market moved from 25% to 70% after debate night" | M | Sparkline on cards, full chart on detail page. Recharts or visx. Time-series data already comes from Gamma + own trades. |
| House market badge ("Featured by [Operator]") | Differentiates house markets from Polymarket mirrors. Builds operator brand | S | Visual treatment + label. Tiny dev cost, big trust signal — "this market is curated by us." |
| Onboarding tour (first-time) | New users get a 4-step tour: browse → bet → portfolio → resolution | M | shadcn-based tour. Reduces "I don't understand prediction markets" bounce. Skippable. |
| Sign-up bonus (e.g., 1000 virtual credits) | Standard play-money pattern (Manifold uses M1000 starter) | S | Automatic credit on email verification. Configurable in admin settings. |
| Position size suggestions ("Kelly-light") | "Bet 5% of balance" quick buttons next to stake input | S | Buttons: 5% / 10% / 25% / Max. Reduces typing. |
| Comment threads on markets | Community discussion. Manifold has this; it's part of why their markets feel alive | L | Markdown comments, replies, like button. Moderate via admin (delete/hide). Spammable — defer if scope tight; explicit antifeature for v1 demo. |
| Watchlist / favorites | "Star markets I'm tracking" | S | Simple join table user_market_watch. Lightweight engagement hook. |
| Search / filter (even simple) | "Find market by keyword or category" | M | If catalog is only top-25 + house, basic search is enough. Postgres `ILIKE` is fine. Per PROJECT.md, full search is explicitly deferred — but a minimal client-side filter is cheap and feels professional. |
| Share market link (Open Graph card) | Social sharing — drives organic acquisition | S | OG image with question + odds. Each market gets a shareable URL. |

### Differentiators — Operator (Where We Sell the Sale)

What makes the operator see XPredict as "a real product" vs "a prototype."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Featured / promoted markets | Operator can pin a house market to the top of the home feed | S | Boolean `featured` + sort field on market. Adminonly toggle. Crucial for editorial control. |
| Bulk recharge | "Give 500 credits to every user who hasn't bet this week" | M | Admin form: filter users → preview → confirm. Logged as a single batch event. |
| Activity timeline per user | "What did this user do in the last 7 days?" | S | Merged view of bets, deposits, logins for one user. Useful for support. |
| Operator notes on users | Free-text annotations attached to a user (visible only to operator) | S | Single text field. Useful for customer support context. |
| Configurable bet limits | Per-user or per-market min/max stakes | M | Settings: global default, per-user override. Prevents whales from breaking play balance. |
| Configurable house edge / spread on house markets | Operator can set initial odds with a spread (effective house take) | M | Required if operator wants to play "the house always wins a little" with virtual currency. Cosmetic in play-money, real later. |
| Dashboard: export-ready PDF/CSV report | Operator brings reports to their boss. PDF = "real product" signal | M | Weekly/monthly summary: volume, users, top markets. Print-friendly. |
| Audit log search with replay | "Show me everything operator-Y did last Tuesday" | M | Filter + chronological view. Replay-able for compliance review. |
| Multi-admin with role separation (v1.5) | Some operators have a markets-creator role separate from a support role | M | Roles: super-admin, market-manager, support. Defer to v1.5; v1 has single admin role. |
| Activity webhooks | Operator wants their own systems (Slack, etc.) notified on new signup, big bet, settlement | M | Outbound webhooks to operator-configured URLs. Signed with HMAC. Defer to v1.5 unless asked. |

### Differentiators — Platform Level

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Compliance hooks (KYC stubs) | Code-level placeholders for future real-money KYC integration. Shows the buyer "this is built to upgrade" | S | Empty `kyc_status` field on user, `compliance_event` table with no producers yet. Zero runtime cost, big "this is production-ready" signal. |
| Stripe integration stub (interface only) | A "Recharge with Stripe" button that goes nowhere, with the code interface ready behind it | S | Disabled UI element + WalletService.recharge() method that accepts a payment_provider param (currently only "manual" valid). Per PROJECT.md decision rationale. |
| Feature flags | Operator can toggle individual modules (leaderboard on/off, comments on/off) | M | Single feature_flags table or env vars. Per PROJECT.md, this preps multi-tenant v2 where each tenant has a different feature mix. |
| API documentation auto-generated | FastAPI gives this free via OpenAPI/Swagger | S | Already free with FastAPI. Showable as "we have a documented API" — useful to operator's tech team. |
| Localization scaffold (es / en) | Per Pol's profile + likely Spanish operator market | M | Next.js i18n routing + `next-intl`. v1 in Spanish + English. Defer additional languages. |

## Anti-Features (Do NOT Build in v1)

These show up as "obvious" feature ideas but are traps for the demo. Each has an explicit alternative.

| Anti-Feature | Why Requested | Why Problematic for v1 | Alternative |
|--------------|---------------|------------------------|-------------|
| Order book / limit orders | "Polymarket has it, we should too" | 5-10x complexity for matching engine + market-making. Only matters for serious traders. Play money users don't need it. | Single-price market orders. Mirror current Polymarket price for synced markets; admin sets price on house markets. |
| Sell position before resolution (cash-out) | "Players want flexibility" | Requires bid/ask spread, AMM or matching engine, complex P&L calculation. Per PROJECT.md explicitly excluded. | Position is held until market resolves. Period. |
| Real-money / fiat / crypto / USDC | "Why would anyone play for fake money?" | Licensing (DGOJ in Spain), KYC, AML, payment processor relationships, custody. Months of legal work. | Play money with production architecture. Stripe stub for the upgrade path. Per PROJECT.md explicit decision. |
| Multi-tenant runtime | "It's white-label, must be multi-tenant" | Adds tenant_id everywhere, RLS policies, per-tenant config, much more complex routing. v1 has ONE operator. | Single-tenant with `tenant_id` ghost column. Explicit refactor cost in v2. Per PROJECT.md decision. |
| Native mobile apps (iOS/Android) | "Modern products are mobile-first" | App store reviews, two more codebases, push notifications infrastructure | Responsive mobile web. Excellent on mobile browsers. Per PROJECT.md explicit out-of-scope. |
| Push notifications | "Engagement!" | Service workers, FCM/APNS, opt-in flow, separate channel per OS | Email for critical events only (verify, reset, big resolution). No promotional push. |
| Marketing email / drip campaigns / referrals | "Growth hacking!" | Compliance (CAN-SPAM, GDPR), email reputation management, A/B framework. Distracts from core. | Single transactional template per event. Defer engagement loops to post-validation. |
| Full Polymarket catalog (10,000+ markets) | "More markets = more value" | Triggers need for search, filters, pagination, categorization — none of which add demo value. Per PROJECT.md decision. | Top 25 mirrored + N house markets. Operator curates the visible catalog. |
| User-created markets (Manifold-style) | "Open market creation is Manifold's superpower" | Moderation queue, spam, abuse, resolution problems on long-tail markets. No fit for B2B2C white-label model where operator controls the catalog. | Only admin (operator) creates house markets. Operator can solicit ideas from users via external channels. |
| Sweepstakes / cash-equivalent prizes | "Adds real-money excitement without licensing" | Sweepstakes laws vary by US state. Manifold spent significant legal work on this. Out of scope for Spanish demo. | Leaderboard glory only. Top forecasters get badges, not prizes. |
| WebSocket-everything | "Real-time is better" | Connection management, scaling, fallback complexity | WebSocket for prices + activity feed. REST polling everywhere else. Specific, not blanket. |
| Live chat (operator-to-user) | "Customer support!" | Real-time infra, agent UI, history, files | Email-only support. `support@operator.com`. Defer chat to validation. |
| Multi-language at v1 (beyond es/en) | "International rollout" | Per-language QA, translator workflow, RTL support, etc. | Two languages (Spanish primary, English secondary) using next-intl. More on demand. |
| Crypto wallets / Web3 sign-in | "Polymarket has it" | Wallet UX is harder than email for non-crypto users; pulls in chain dependencies; doesn't match play-money model | Email + password. Period. (Possible passkeys/WebAuthn in v2.) |
| Real-time dispute system with user staking | "Polymarket has UMA" | UMA is on-chain and complex; replicating it off-chain is a project unto itself | Admin manual override for stuck markets. Logged. Two-step confirm. |

## What Makes a Prediction Market Platform Feel Trustworthy (Critical Section)

Play money is the v1 model, but the platform must *look* and *feel* like a real one. Operators will not buy a product that looks like a school project. Here are the trust signals — most are cheap to ship, but enormous in perception.

### Visual / UX Trust Signals

| Signal | Why It Builds Trust | Implementation |
|--------|---------------------|----------------|
| Real-time price updates that never stall | "Stale prices = product is broken" (industry quote) | WebSocket + retry/reconnect logic. Visible "Live" indicator. |
| Visible resolution source on every market | Players need to know "who decides if this is YES or NO" | Mirrored: "Resolves via Polymarket / UMA Oracle" with link. House: "Resolves manually by [Operator Name] on [date]" with criteria text. |
| Probability shown as percentage AND price | Two ways to read the same number = professional polish | "72% YES" + "$0.72" both visible. |
| Crisp, professional design system | Generic Tailwind = "another bootstrap demo." Polished shadcn + custom palette = "real product" | shadcn/ui + per-operator color tokens. Dark mode optional but expected. |
| Clear settlement messaging | "When this resolves YES, you receive $X" before bet, "Resolved YES on [date], you received $X" after | Pre-bet confirmation copy + post-settlement notification card. |
| Currency symbol & format consistency | $1,234.56 vs 1234.56 PTS = the latter feels childish | Use $ symbol consistently. Configurable per operator (e.g., €). NEVER use "points" or "tokens" in the player-facing UI. |
| No "this is play money" disclaimer in main UI | The whole point is to make it feel real | Single disclaimer in T&C and footer. Never in the bet flow. Maybe a subtle "demo balance" badge in admin tools, not for players. |

### Architectural / Operational Trust Signals

| Signal | Why It Builds Trust | Implementation |
|--------|---------------------|----------------|
| Double-entry accounting | Every cent traceable. Every balance reconstructable. Industry standard | Two-account ledger (per PROJECT.md). Build it right from day 1. |
| Immutable audit log | "Every action is recorded and unchangeable" | Append-only. Never UPDATE/DELETE. Operator-visible. |
| Transactions on bet placement | A bet must either fully succeed or fully fail. No partial states | Postgres transactions wrapping wallet + position + log entries. |
| Production-grade auth | Argon2 + secure sessions, not MD5 + cookies | FastAPI-users with modern defaults. |
| Email verification before betting | "Anti-abuse" pattern players recognize | Required before first bet (configurable per operator). |
| Visible balance + balance history | Players see exactly how their money moved | Wallet ledger displayed transparently. |
| Resolution audit trail | When operator resolves a house market, they must add a justification — visible to players | "This market was resolved YES on 2026-06-03 because [...]" — published with the resolution. |
| Stripe / payment provider stub | "Real money is one config change away" — sells the upgrade path | Disabled "Deposit via card" UI. Service interface ready. Per PROJECT.md. |
| Healthcheck endpoint + status page (v1.5) | "We monitor uptime" | `/health` endpoint first; public status page later. |
| Transactional emails come from the operator brand | `noreply@operator.com` not `noreply@xpredict.io` | Configurable SMTP sender per instance. |

## Feature Dependencies

```
Auth (login/register/session)
    |-- requires --> User model + email verification
    |-- requires --> Argon2 + session/JWT infra
    |
    +-- enables -->  Wallet (one per user)
                        |-- requires --> Double-entry ledger
                        |-- requires --> Audit log
                        |
                        +-- enables -->  Bet placement
                                            |-- requires --> Market entity
                                            |-- requires --> Position entity
                                            |-- requires --> ACID tx (wallet debit + position insert)
                                            |
                                            +-- enables -->  Settlement
                                                                |-- requires --> Resolution event
                                                                |-- requires --> ACID tx (wallet credit + position close)
                                                                |
                                                                +-- enables -->  P&L history, leaderboard, calibration

Market entity
    |-- two sources -->  Polymarket sync  (background poller, auto-resolution)
    |                    House markets    (admin CRUD, manual resolution)
    |
    +-- enables -->  Market list page, market detail page, portfolio (via positions)

Admin role + auth
    |-- requires --> Role on user model + admin route guards
    |
    +-- enables -->  CRM (user list, recharge, ban)
                     House market CRUD
                     Manual resolution
                     Audit log viewer
                     Dashboard KPIs

Branding config (single-row settings)
    |-- enables -->  Logo, palette, email sender on every UI surface
    |
    +-- prepares --> Multi-tenant v2 (tenant_id ghost column promotes to live)

Polymarket Gamma sync
    |-- requires --> Celery + Redis (queue)
    |-- requires --> HTTP client + retry logic
    |
    +-- enables -->  Mirrored markets
                     Auto-resolution of mirrored markets
                     Price history (snapshots over time)
```

### Critical Dependency Notes

- **Wallet ledger MUST exist before any bet feature.** Skipping this and "adding it later" causes a rewrite. Per PROJECT.md "production-grade desde v1."
- **Audit log MUST exist before any state-changing admin action.** Operators expect to see "who did what when" from day one of the demo. Adding logging retroactively is unreliable.
- **`tenant_id` ghost column MUST be on the schema from day one.** Adding it later means a migration of every player-owned table. Cheap now, expensive later. Per PROJECT.md decision.
- **WebSocket plumbing is required for the "feels real" demo.** Polling everywhere makes the UX feel like a 2010 product. Build the WebSocket layer before bet placement so prices animate on the first demo.
- **Polymarket sync is a separate worker concern.** It should not block bet placement, login, or any user-facing flow if the Gamma API is slow. Use Celery + last-known-good cache.

## MVP Definition (v1 — Sales Demo)

### Launch With (v1.0) — Required for the First Sales Demo

These are the features without which the demo fails or the buyer says "this is incomplete."

**End-user side:**
- [ ] Register / login / logout / password reset / email verify (Production-grade auth)
- [ ] Market list / browse home (with top-25 Polymarket + featured house markets)
- [ ] Market detail page (question, criteria, price chart, order entry, recent activity)
- [ ] Buy YES / Buy NO at current price (no order book)
- [ ] Wallet balance display + transaction history
- [ ] Portfolio page (open positions + settled positions + P&L)
- [ ] Real-time price updates via WebSocket
- [ ] Resolution display (outcome, source, settlement details)
- [ ] Responsive mobile web
- [ ] Polished empty / loading / error states
- [ ] Sign-up bonus (configurable, e.g. 1000 virtual currency units)

**Operator/admin side:**
- [ ] Admin login (separate role)
- [ ] User list + search + detail view
- [ ] Manual recharge balance (with reason field)
- [ ] Ban/unban user
- [ ] House market create / edit / close
- [ ] House market manual resolution (with justification text)
- [ ] Market list (admin view, all sources)
- [ ] KPI dashboard (volume, DAU, active markets, pending resolutions, house P&L)
- [ ] Audit log viewer (read-only)
- [ ] Force-settle / override for stuck markets (with confirm + log)
- [ ] CSV export (users, transactions, bets)

**Platform side:**
- [ ] Double-entry ledger
- [ ] Immutable audit log
- [ ] ACID transactions on bet + settle
- [ ] Rate limiting (auth + bet)
- [ ] Configurable branding (logo, palette, brand name)
- [ ] Polymarket Gamma API sync (Celery worker)
- [ ] Transactional email (verify, password reset)
- [ ] Stripe stub interface (for upgrade-path signal)
- [ ] `tenant_id` ghost column on schema
- [ ] Feature flags scaffold

### Add After Validation (v1.5) — After First Sale or Strong Demo Feedback

Things to ship once v1.0 is validated and we have a buyer or strong signal.

- [ ] Global leaderboard (weekly + all-time) — turns play money into status game
- [ ] Probability history chart on market detail
- [ ] Live activity feed on market detail (anonymized trade stream)
- [ ] Watchlist / favorites
- [ ] Onboarding tour for first-time users
- [ ] Bulk recharge (admin)
- [ ] Multi-admin with role separation (market-manager vs support)
- [ ] Outbound webhooks (operator-configured)
- [ ] Operator notes on users
- [ ] Featured/promoted markets toggle (admin)
- [ ] PDF report export (weekly/monthly)
- [ ] Localization scaffold (es + en)

### Future Consideration (v2+) — After Product-Market Fit Established

These require business commitment beyond a single demo.

- [ ] Multi-tenant runtime (promote `tenant_id` to live with RLS)
- [ ] Stripe live integration (real money) — requires licensing project
- [ ] KYC integration (Onfido / Sumsub) — paired with real money
- [ ] Brier score / calibration rating
- [ ] Comment threads
- [ ] Order book / limit orders / secondary market
- [ ] Native mobile apps (iOS, Android)
- [ ] Push notifications
- [ ] Referral program
- [ ] live-bets integration (per PROJECT.md timeline)
- [ ] AI-suggested markets (operator tool: "we noticed users are searching for X, create a market?")
- [ ] Prediction tournaments / leagues / seasons (Manifold-style)

## Feature Prioritization Matrix (v1 Decision Set)

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Production auth (register / login / reset) | HIGH | MEDIUM | P1 |
| Double-entry ledger | HIGH (foundation) | HIGH | P1 |
| Audit log | HIGH (foundation) | MEDIUM | P1 |
| Market list + detail page | HIGH | MEDIUM | P1 |
| Buy YES/NO bet flow | HIGH | MEDIUM | P1 |
| Portfolio + transaction history | HIGH | MEDIUM | P1 |
| Real-time price updates (WebSocket) | HIGH | MEDIUM | P1 |
| Polymarket Gamma sync | HIGH | MEDIUM | P1 |
| House market admin CRUD + resolution | HIGH (operator demand) | MEDIUM | P1 |
| Admin: user list / recharge / ban | HIGH (operator demand) | LOW-MEDIUM | P1 |
| Admin KPI dashboard | HIGH (operator demand) | MEDIUM | P1 |
| Branding config | HIGH (sales pitch) | LOW | P1 |
| Stripe stub interface | MEDIUM (signal only) | LOW | P1 |
| `tenant_id` ghost column | LOW (now) / HIGH (later) | LOW | P1 |
| Leaderboard | HIGH (engagement) | MEDIUM | P2 |
| Probability history chart | MEDIUM (polish) | LOW-MEDIUM | P2 |
| Live activity feed | MEDIUM (polish) | MEDIUM | P2 |
| Onboarding tour | MEDIUM (retention) | MEDIUM | P2 |
| Bulk recharge | LOW (now) / MEDIUM (later) | LOW | P2 |
| Multi-admin roles | LOW (now) / HIGH (scale) | MEDIUM | P2 |
| Brier score / calibration | LOW (niche) / HIGH (advanced users) | HIGH | P3 |
| Comments | LOW | HIGH (moderation cost) | P3 |
| Multi-tenant runtime | LOW (v1) | HIGH | P3 (v2 only) |
| Real money / Stripe live | OUT OF SCOPE v1 | VERY HIGH | OUT |
| Mobile native apps | OUT OF SCOPE v1 | VERY HIGH | OUT |

**Priority key:** P1 = launch (v1.0). P2 = follow-up (v1.5). P3 = future (v2+). OUT = out of scope.

## Competitor Feature Analysis

| Feature | Polymarket | Kalshi | Manifold | DraftKings (sportsbook) | XPredict approach (v1) |
|---------|------------|--------|----------|-------------------------|------------------------|
| Money type | Real (USDC, crypto) | Real (USD, fiat) | Play (Mana) | Real (USD) | Play (virtual credits) |
| Onboarding | Wallet connect or email + KYC (US) | Email + ID + SSN + KYC | Email only | Email + ID + age check | Email + verification, no KYC |
| Market sources | Internal team + UMA oracle | Internal proposal/approval | Any user can create | Internal sports markets | Mirrored from Polymarket + house (admin) |
| Resolution | UMA optimistic oracle | Manual review by Kalshi | Market creator + dispute system | Internal sports data | Polymarket UMA for mirrors, manual for house |
| Order entry | Order book + AMM | Order book | AMM (no order book) | Single-price odds | Single-price market orders (no order book) |
| Cash-out / sell | Yes (via order book) | Yes (via order book) | Yes (sell shares) | Yes (cash-out feature) | NO — held to resolution (per PROJECT.md) |
| Portfolio / P&L | Yes, detailed | Yes, detailed | Yes, with calibration | Yes, basic | Yes (positions + P&L + transactions) |
| Leaderboard | Third-party only | No | Yes (built-in, big feature) | No (private) | Yes (v1.5) |
| Comments / social | No | No | Yes (Reddit-style) | No | No (v1), maybe v2+ |
| Calibration scoring | No | No | Yes (Brier score) | No | No (v1), maybe v2+ |
| Real-time prices | Yes (WebSocket) | Yes (WebSocket) | Yes | Yes | Yes (WebSocket) |
| Admin/operator panel | Internal only | Internal only | Internal only | Internal only | First-class (this is our buyer) |
| Branding configurable | No | No | No | No | Yes (this is our wedge) |
| Multi-tenant | No | No | No | No | v1: single-tenant w/ ghost column; v2: real |
| Mobile native app | Yes | Yes | Yes | Yes | No (web only — PROJECT.md) |

**Key takeaway:** XPredict's wedge is not features that compete with Polymarket on depth. It's **operator-first features** (admin, CRM, branding, audit) — which none of the reference products expose because they *are* the operator. We are building the operator experience as a product.

## Open Questions for Requirements Phase

These need answers before final REQUIREMENTS.md, but are explicit research findings rather than guesses:

1. **Configurable bet limits per user / per market?** Industry-standard, but PROJECT.md doesn't mention it. Recommend yes, global default with override.
2. **Email verification before betting, or before all activity?** Common pattern is "after register but before first bet" (allows browsing). Recommend this.
3. **What happens to user balance when banned?** Frozen (kept, can't bet) vs. zeroed? Recommend frozen + admin can refund/zero manually with audit.
4. **Default starting bonus?** Manifold gives M1000. Recommend operator-configurable, default 1000 virtual units, with first-resolution bonus configurable.
5. **How are mirrored markets visually distinguished?** Recommend a "Synced from Polymarket" badge with the Polymarket logo, plus a link to the original — adds credibility ("we're not making up these odds").
6. **Resolution justification visibility on house markets?** Recommend public to players (transparency = trust), not just internal.
7. **CSV exports: behind admin login only, or also via API?** Recommend admin-UI only in v1 (no public API). Webhooks/API for v1.5+.
8. **Are there *any* situations where the operator can edit a user's transaction history?** No — recommend immutable. Mistakes get correcting entries (adjustments), never deletions. This is a core trust property.
9. **What does the operator see when they sign in?** Recommend KPI dashboard as the default landing page — sets tone of "this is a business tool, not a toy."

## Sources

### Reference Products Analyzed
- [Polymarket Review: Features, Betting Options, and User Experience (Tribuna)](https://tribuna.com/en/betting/blogs/polymarket-review-features-betting-options-and-user-experien/)
- [Polymarket — The World's Largest Prediction Market](https://polymarket.com/)
- [Polymarket Portfolio Documentation](https://docs.polymarket.us/api-reference/portfolio/overview)
- [Polymarket KYC Verification Flow](https://docs.polymarket.us/institutional/kyc/verification-flow)
- [Polymarket UMA Oracle Resolution Process](https://help.polymarket.com/en/articles/13364518-how-are-prediction-markets-resolved)
- [Kalshi vs Polymarket: Comparison (Next.io)](https://next.io/prediction-markets/guide/kalshi-vs-polymarket/)
- [Kalshi vs Polymarket: Which is Better (Covers)](https://www.covers.com/betting/prediction-sites/polymarket-vs-kalshi)
- [Kalshi Mandatory KYC and Surveillance](https://kalshi.com/market-integrity/kyc-surveillance)
- [Manifold Markets — homepage](https://manifold.markets/)
- [Manifold FAQ](https://docs.manifold.markets/faq)
- [Manifold Markets Review 2026 (CryptoSlate)](https://cryptoslate.com/prediction-markets/manifold-predictions-review/)
- [Manifold Leagues](https://manifold.markets/leagues)
- [Manifold Markets Community Review (mytopsportsbooks)](https://www.mytopsportsbooks.com/prediction-markets/manifold-review/)

### Industry References — Design / UX / Architecture
- [Best UX/UI Patterns for Prediction Markets (Avark)](https://avark.agency/learn/prediction-market-design-patterns)
- [How Prediction Market Order Books Work on Kalshi and Polymarket (DeFi Rate)](https://defirate.com/prediction-markets/how-order-books-work/)
- [How Prediction Markets Settle (DeFi Rate)](https://defirate.com/prediction-markets/how-contracts-settle/)
- [Sports Betting UI/UX Strategic Guide (GammaStack)](https://www.gammastack.com/blog/sports-betting-ui-ux-guide/)
- [Sportsbook UX Best Practices (Symphony Solutions)](https://symphony-solutions.com/insights/sportsbook-ux)
- [Sportsbook UI Design (Studio Ubique)](https://www.studioubique.com/work/sportsbook-ui-design/)
- [UX Playbook 2025 (Shape Games)](https://www.shapegames.com/news/ux-best-practices-playbook)

### Industry References — Operator / White Label / KPIs
- [Prediction Markets White Label Platform (Leverate)](https://leverate.com/prediction-markets-white-label/)
- [White Label Prediction Markets (Tradesmarter)](https://www.tradesmarter.com/prediction-markets.html)
- [Prediction Market Software (Vinfotech)](https://www.vinfotech.com/prediction-market-software)
- [White Label SaaS Architecture (Developex)](https://developex.com/blog/building-scalable-white-label-saas/)
- [Essential KPIs for Sports Betting Dashboards (InTarget)](https://intarget.space/blog/essential-kpis-for-sports-betting-dashboards/)
- [iGaming KPIs (Scaleo)](https://www.scaleo.io/blog/10-kpis-every-igaming-company-should-measure-track/)
- [Gamification in Sports Betting (BetConstruct)](https://www.betconstruct.com/product-blog/best-gamification-elements-in-sports-betting-software-to-engage-players)

### Industry References — Wallet / Ledger / Compliance
- [Double-Entry Bookkeeping in Ledger Systems (Medium)](https://medium.com/@altuntasfatih42/how-to-build-a-double-entry-ledger-f69edcea825d)
- [What Is a Double-Entry Ledger in Fintech (SDK.finance)](https://sdk.finance/blog/what-is-a-double-entry-ledger-in-fintech/)
- [Token Ledger (Ruby implementation reference)](https://github.com/wuliwong/token_ledger)
- [Inside UMA Oracle (Rocknblock)](https://rocknblock.io/blog/how-prediction-markets-resolution-works-uma-optimistic-oracle-polymarket)

---
*Feature research for: white-label prediction market platform (XPredict)*
*Researched: 2026-05-25*
*Confidence: HIGH — multi-source verified against Polymarket, Kalshi, Manifold Markets, and white-label SaaS industry references*
