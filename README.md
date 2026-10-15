# McXus

Privacy-first super app for Papua New Guinea and the Pacific: private messaging, a marketplace, and Stars
payments protected by escrow.

> **Status: M1 money core and M2 marketplace (passed) + M3 encrypted chat and Compose app (in review) — sandbox.** Test Stars only; no real money moves until a licensed issuer
> partner is connected (see [ADR 0001](docs/decisions/0001-stars-as-e-money-sandbox-first.md)).

## What is in this module

| Area | What it does |
|---|---|
| Sign-in | Phone number + 6-digit SMS code (console SMS stub), JWT tokens, staff roles |
| Stars wallet | Balance, statement, KYC tier limits, sandbox top-up, deposits (maker-checker), withdrawals |
| Ledger | Double-entry, append-only (enforced by the database), every entry balanced, integrity and BPNG trust-reconciliation reports |
| Escrow | Order state machine: pay → seller accepts within 20 min → dispatch → handover PIN / buyer confirms / auto-release after 7 days; cancellations, penalties, disputes with partial refunds |
| Worker | Applies the 20-minute and 7-day timers every 30 seconds |
| Marketplace (M2) | Listings with up to 5 photos, PNG provinces/districts/suburbs, search, first-buyer-to-pay stock reservation, ratings, seller trust badges, reports and moderation |
| Messaging (M3) | End-to-end encrypted 1:1 chats (OpenMLS / MLS RFC 9420): the server relays and stores ciphertext only, 30-day expiry, long-poll delivery; chat with a seller from any listing |
| Android app (M3) | Jetpack Compose: Chats · Discover · Market · Wallet · Me, escrow order cards in chat, handover QR + PIN |
| Groups & media (M3.2) | Encrypted group chats up to 256 people (admins, add/remove/leave), encrypted photos and voice notes, content-free push via Firebase (ADR 0010) |
| Disputes & staff console (M4) | Three-stage disputes (agree 3 days → mediator 5 PNG working days → appeal), offers, statements and photos, in the app and in a staff web console with every staff task and an audit log (ADR 0011) |
| Places (M3.1) | Meet-up / delivery points: GPS (current location or map) first, landmark second; on listings, orders and in chat (ADR 0009) |

1 Star = K1. All amounts are exact decimals, sent and returned as strings (`"150.00"`).

## Quick start (Windows, Docker Desktop)

```powershell
.\start-dev.ps1          # builds and starts db + api + worker + staff console, creates demo users, opens the API docs
.\run-tests.ps1          # tests, lint, type check, dependency audit
python scripts\smoke_test.py   # walks one order end to end against the running API
```

Get a sign-in token for a demo user (sandbox only), then click **Authorize** in http://localhost:8000/docs:

```powershell
docker compose exec api python -m app.cli dev-token 70000001
```

Demo users: buyer `70000001`, seller `70000002`, finance A `70000003`, finance B `70000004`,
mediator `70000005`, admin `70000006`, moderator `70000007`, compliance `70000009`, KYC `70000010`, support `70000011`.

Staff console (disputes, deposits and payouts, reported listings, people, reports, staff activity):
http://localhost:8080. Sign in with a staff number; the sandbox fills in the code. Sample disputes:
`docker compose exec api python -m app.cli seed-disputes`. Details: [admin/README.md](admin/README.md). Step-by-step review: [docs/TESTING-GUIDE.md](docs/TESTING-GUIDE.md).

## Android app

Open the folder in VS Code, plug in the phone (USB debugging on) and press **Ctrl+Shift+B** to build, install and
open McXus. All tasks and the phone smoke test: [android/README.md](android/README.md).

## Configuration

All settings are `MCXUS_*` environment variables; copy `backend/.env.example` to `backend/.env`. Fees, limits
and timers are configuration, not code. In production (`MCXUS_ENV=prod`) the API refuses to start with dev
secrets or with sandbox mode on.

## Layout

```
backend/app/
  ledger/service.py    double-entry ledger, reports
  wallet/service.py    deposits, withdrawals, sandbox top-up, limits
  escrow/service.py    order state machine and all escrow money movements
  escrow/fees.py       fee rules (pure functions)
  marketplace/         listings, search, photos, stock, reviews, trust, moderation
  disputes/            three-stage disputes: offers, evidence, mediator, appeal; PNG working days
  messaging/           MLS delivery service: devices, key packages, conversations, ciphertext relay
  auth/                phone OTP, JWT, role checks
  api/                 HTTP routes and request/response schemas
  jobs.py              timer worker
  audit.py             staff activity log
  cli.py               make-admin, seed-demo, seed-disputes, dev-token
backend/migrations/    Alembic (0001 money core; 0002 marketplace + PNG seed data; 0003 messaging; 0004 locations; 0005 groups/media/push; 0006 key devices; 0007 disputes + staff log)
backend/tests/         128 tests against real PostgreSQL
crypto/                Rust: OpenMLS wrapper + Kotlin bindings (UniFFI) for the app
android/               Kotlin + Jetpack Compose app
admin/                 staff console: React + TypeScript + Vite + Tailwind (shadcn/ui-style), nginx in Docker
.vscode/tasks.json     build / install / test on a USB phone from VS Code
docs/                  architecture, decisions (ADRs), testing guide
```

## Backup and restore (sandbox)

```powershell
docker compose exec -T db pg_dump -U mcxus -Fc mcxus > backups\mcxus-$(Get-Date -f yyyyMMdd-HHmm).dump
docker compose exec -T db pg_restore -U mcxus -d mcxus --clean < backups\<file>.dump
```

## Licence

Apache-2.0 — see [LICENSE](LICENSE). Copyright 2026 Jerry Badu.
