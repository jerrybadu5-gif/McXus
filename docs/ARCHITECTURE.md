# McXus architecture

Full requirements: Developer project doc `mcxus-requirements.md`. This file covers what is built.

## Target system (all modules)

```
Android app (Kotlin) ──HTTPS──> Caddy ──> Core API (FastAPI) ──> PostgreSQL (core, ledger)
        │                                   └── worker (timers)
        └──── E2EE messaging ──> McXus messaging server (module M3, own build on audited crypto libs)
Admin console (React, staff only) ──> Core API
Payment rails (bank statement matching → card → mobile money → cash agents) ──> adapters ──> ledger
```

## Build order

| Module | Scope | Status |
|---|---|---|
| M0 | Repo, compose, CI, phone sign-in, roles | **done (in this module)** |
| M1 | Ledger, wallet (sandbox), escrow, fees, timers | **done — passed 14/10/2026 (PR #1)** |
| M2 | Marketplace: listings, photos, search, locations, stock reservation, reviews, trust score, reports | **built — awaiting Jerry's review** |
| M3 | Messaging server + Android app (1:1, groups, media, E2EE, key backup), chat-with-seller | |
| M4 | Disputes (3-stage, evidence), admin console | |
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
