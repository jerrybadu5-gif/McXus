# ADR 0011: Three-stage disputes and the staff console (M4)

Status: built 15/10/2026 (Jerry chose all four recommended options)

## Decisions

| Question | Decision |
|---|---|
| Stages | Negotiate (3 days) → mediator (5 PNG working days) → appeal (3 days to appeal; a senior staff member decides, final) |
| Evidence | Written statements and photos (up to 20 statements and 5 photos per person). Readable by both parties and staff |
| Console | All staff tasks: disputes, deposits (maker-checker) and payouts, reported listings, people (verification level, staff role, freeze), money reports, staff activity log |
| App | Buyer and seller dispute screens in the Android app |

## How a dispute runs

```
order DISPUTED: the Stars stay in escrow; no auto-release
 1 negotiation   3 days. Either side offers "the buyer gets back K__" (the seller gets the rest).
                 Accepting an offer settles it at once. Either side can ask for a mediator earlier.
 2 mediation     5 PNG working days (end of the 5th working day, 17:00 Port Moresby). A mediator takes
                 the case, reads both sides and decides a refund (0 to the full amount) with a reason.
                 The parties can still settle with an offer until the decision.
 3 decided       The decision is final when the 3-day appeal window ends, or sooner if both accept.
   appeal        Either side may appeal once (not after accepting). A compliance officer or admin who did
                 not make the first decision makes the final decision.
 resolved        One ledger entry: refund to the buyer, the rest to the seller less the 3% escrow fee
                 (owed penalties recovered first), exactly like a normal release.
```

- Money moves only at the end, through `escrow.settle_dispute` (the same `_release` as a normal sale).
- Nobody can decide a dispute they are part of; the appeal must be decided by someone other than the mediator.
- The worker applies the deadlines: negotiation → mediation after 3 days; decided → resolved after the appeal window.
  A late mediator is not automatic: the case is flagged red in the console ("past the mediator deadline").
- PNG public holidays (New Year, Good Friday, Easter Saturday and Monday, King's Birthday (2nd Monday of June),
  23 July, 26 August, 16 September, Christmas, Boxing Day) are built in; declared holidays go in
  `MCXUS_EXTRA_HOLIDAYS`. Check the list each year against the gazette.
- Disputes opened before M4 were moved to the mediator stage with a 7-day deadline by migration 0007.

## Privacy and records

- Dispute evidence is **not** end-to-end encrypted: the mediator must read it, so the app says so before upload.
  Photos are re-encoded on the server, which removes GPS and all other metadata, and are stored in a private
  folder (`MCXUS_EVIDENCE_DIR`, a Docker volume) served only to the two parties and staff.
- Evidence and the timeline are kept with the order record (7 years, like other financial records).
- Encrypted chat stays private: staff never see chat messages. If a party wants a chat message considered, they
  add it as a statement or a screenshot photo themselves.

## Staff console

- React + TypeScript + Vite + Tailwind with shadcn/ui-style components (Radix), in `admin/`. Served by nginx in
  Docker on `127.0.0.1:8080` (or the free port in `MCXUS_ADMIN_PORT`), which forwards `/v1` to the API (same origin; strict Content-Security-Policy).
- Staff sign in with their phone and a code, like the app. Customer accounts are turned away. The token is kept
  in sessionStorage (gone when the tab closes).
- Each role sees only its parts (the API enforces the same): support (disputes read-only, people), mediator
  (disputes), compliance (appeals, freeze accounts, reports, staff activity), finance (deposits, payouts,
  reports), kyc (people, verification level), moderator (reported listings), admin (everything, staff roles).
- Every staff action that changes something is written to `staff_actions` (who, what, which record, detail).

## M4.1 (Jerry's review, 15/10/2026)

- Dispute news reaches the other party three ways: a dispute card in their buyer–seller chat (sent end-to-end
  encrypted by the person who acted, so the usual chat notification fires), a red badge on Me and Me › Disputes
  (`GET /v1/disputes/attention`: a new dispute, an offer from the other side, or a decision to accept or appeal),
  and a phone notification once per new update (content-free push wakes the app; it asks the server).
- Several photos can be picked at once (disputes 5, chat 10, listings 5).
- Discover › Message and a listing's Chat attach the listing above the message box; it is sent with the message.
- People search (console and app) is not case-sensitive, matches words in any order and suggests as you type.
  Customers search names from 2 letters, or a (nearly) complete phone number; results show only the name and the
  last 3 digits of the phone.
- Freezing is a case with a reason (`account_freezes`): the frozen person can still sign in to read why and appeal
  once; someone other than the staff member who froze it decides (unfreeze, or keep frozen with a reason).
  The console lists frozen accounts, appeals first. Migration 0008 opens a case for accounts frozen earlier.

## Known limits

- No SMS/push to the parties when the stage changes yet: the app checks the dispute every 20 seconds while open,
  and the order shows "In dispute". Notifications come with the SMS provider (M7) and push.
- The console has no two-person approval for dispute decisions (the appeal is the check). Large refunds may need
  maker-checker later.
- Staff sign-in uses the same phone OTP as customers; add a second factor (TOTP) before any real money.
