# McXus architecture

Full requirements: Developer project doc `mcxus-requirements.md`. This file covers what is built.

## Target system (all modules)

```
Android app (Kotlin) ──HTTPS──> Caddy ──> Core API (FastAPI) ──> PostgreSQL (core, ledger)
        │                                   └── worker (escrow timers, dispute deadlines, chat expiry)
        └──── E2EE messaging ──> McXus messaging server (module M3, own build on audited crypto libs)
Staff console (React, nginx :8080, staff only) ──/v1──> Core API
Payment rails (bank statement matching → card → mobile money → cash agents) ──> adapters ──> ledger
```

## Build order

| Module | Scope | Status |
|---|---|---|
| M0 | Repo, compose, CI, phone sign-in, roles | **done (in this module)** |
| M1 | Ledger, wallet (sandbox), escrow, fees, timers | **done — passed 14/10/2026 (PR #1)** |
| M2 | Marketplace: listings, photos, search, locations, stock reservation, reviews, trust score, reports | **done — PR #5** |
| A0 | Android preview (plain Kotlin): sign-in, market, sell + photos, buy, orders + handover PIN/QR, wallet | **done — folded into #5** (ADR 0007) |
| M3 | Messaging server + chat in the Android app (1:1, groups, media, E2EE), chat-with-seller, places | **done — PRs #7, #8** (ADR 0008–0010) |
| M4 | Disputes (3-stage, offers, evidence, appeal), staff console, audit log | **built — awaiting Jerry's test** (ADR 0011) |
| M5 | Status/posts, channels, calls | |
| M6 | Premium privacy, subscriptions, ads, promoted listings, gifting (T2+) | |
| M7 | Real payment rails + partner issuer go-live | |

## Ledger

Chart of accounts (normal side in brackets):

| Code | Kind | Meaning |
|---|---|---|
| `SYS:TRUST_BANK` | asset (D) | Customer money held at the partner bank's trust account |
| `SYS:ESCROW` | liability (C) | Stars locked in open orders (per-order balance via `journal_entries.order_id`) |
| `SYS:WITHDRAWALS_PENDING` | liability (C) | Approved withdrawals not yet paid by the bank |
| `SYS:FEE_REVENUE` | revenue (C) | Escrow, cancellation and withdrawal fees |
| `USR:<id>:WALLET` | liability (C) | A user's Stars |
| `USR:<id>:RECEIVABLE` | asset (D) | Penalties a seller owes, recovered from their next sale |

Guarantees:
- `postings`, `journal_entries` and `order_events` reject UPDATE, DELETE and TRUNCATE (database triggers).
- A deferred constraint trigger rejects any entry whose debits ≠ credits at commit.
- Accounts are locked (in id order) before balances change, so concurrent payments cannot overspend (tested).
- `GET /v1/admin/reports/integrity` re-derives every balance from postings.
- `GET /v1/admin/reports/trust-reconciliation` shows customer funds against the trust account
  (BPNG Directive on Payment Instruments 10.3–10.4, 12.1(c)).

## Escrow money movements

| Event | Journal entry |
|---|---|
| Buyer pays | D buyer wallet, C escrow |
| Release (PIN / confirm / auto) | D escrow; C seller wallet (amount − 3% fee − owed penalties); C fee revenue; C seller receivable |
| Buyer cancels after paying | D escrow; C buyer (amount − 5% fee); C seller ½ fee; C revenue ½ fee |
| Seller rejects within 20 min, window passes, or cancels accepted order within 25 min of payment | D escrow; C buyer full amount (no fees) |
| Seller cancels accepted order 25+ min after payment | D escrow; C buyer full amount + ½ fee; D seller wallet (what they have) and D seller receivable (the rest); C revenue ½ fee |
| Dispute resolved | D escrow; C buyer refund; C seller (rest − fee on rest); C revenue |

## Security notes
- Phone OTP codes and handover PINs are stored only as HMAC-SHA256 hashes, with attempt limits.
- Role checks are server-side on every staff route; maker-checker on deposits (enforced in code and by a DB constraint).
- Money actions accept an `Idempotency-Key` so retries on bad connections never move money twice.
- Production refuses dev secrets and sandbox mode.

## Marketplace (M2)

Tables: `locations` (province > district > suburb), `categories` (two levels, `banned` flag), `listings`
(price, stock, condition, delivery options, location, status, generated `search_tsv` + GIN index),
`listing_photos`, `reviews` (one per order), `listing_reports`. Orders gain `listing_id`, `quantity`,
`stock_reserved`.

Listing status: `active` → `sold_out` (stock 0) / `paused` / `closed` (seller) / `under_review` (3 reports) /
`removed` (moderator). Public: `active` and `sold_out`.

Stock: reserved inside the pay transaction under a row lock on the listing (first payer wins); released inside
the same transaction as any refund. See ADR 0006.

## Messaging (M3)

Tables: `devices`, `key_packages` (one-time, claimed with `FOR UPDATE SKIP LOCKED`), `conversations`
(`kind=direct`, unique `pair_key`, `mls_ready_by` = who sent the accepted Welcome, optional `listing_id`),
`conversation_members`, `mls_messages` (`welcome` | `commit` | `application`, opaque bytes, `expires_at` = +30 days).
Welcomes are visible only to their recipient. The worker deletes expired messages; money records are never touched.

API: `POST /v1/devices`, `POST /v1/keys`, `GET /v1/keys/count`, `POST /v1/keys/claim`, `POST /v1/users/lookup`,
`POST|GET /v1/conversations`, `POST /v1/conversations/{id}/welcome`, `POST /v1/conversations/{id}/messages`,
`GET /v1/messages/sync?after=&wait=` (long-poll, max 25 s). Phone side: `chat/ChatEngine.kt`. Details: ADR 0008.

## Meet-up and delivery location (M3.1)

`listings.latitude/longitude/meetup_address` (seller's public meet-up point) and
`orders.delivery_method/delivery_latitude/delivery_longitude/delivery_address` (visible to buyer and seller).
GPS first, landmark second; points must be inside PNG. Changes are logged as order events. See ADR 0009.

## Groups, media and push (M3.2)

`conversations.kind='group'` with `title` and `epoch`; `conversation_members.role` (admin|member);
`mls_messages.kind` adds `event` (server notice: added/removed/left) and `epoch` on commits; `media_blobs`
(encrypted chat files in the private `MCXUS_BLOB_DIR`, 30-day expiry); `devices.push_token`.
API: `POST /v1/groups`, `GET|PUT /v1/groups/{id}`, `POST /v1/groups/{id}/members` (commit + welcome, epoch-checked),
`POST /v1/groups/{id}/members/remove`, `POST /v1/groups/{id}/leave`, `POST /v1/groups/{id}/role`,
`POST /v1/conversations/{id}/blobs`, `GET /v1/blobs/{id}`, `POST /v1/devices/{id}/push-token`. Push sender:
`app/push.py` (FCM HTTP v1, data-only `{"t":"sync"}`). See ADR 0010.
