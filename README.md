# McXus

Privacy-first super app for Papua New Guinea and the Pacific: private messaging, a marketplace, and Stars
payments protected by escrow.

> **Status: M1 money core (passed) + M2 marketplace and Android preview (in review) — sandbox.** Test Stars only; no real money moves until a licensed issuer
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

1 Star = K1. All amounts are exact decimals, sent and returned as strings (`"150.00"`).

## Quick start (Windows, Docker Desktop)

```powershell
.\start-dev.ps1          # builds and starts db + api + worker, creates demo users, opens the API docs
.\run-tests.ps1          # tests, lint, type check, dependency audit
python scripts\smoke_test.py   # walks one order end to end against the running API
```

Get a sign-in token for a demo user (sandbox only), then click **Authorize** in http://localhost:8000/docs:

```powershell
docker compose exec api python -m app.cli dev-token 70000001
```

Demo users: buyer `70000001`, seller `70000002`, finance A `70000003`, finance B `70000004`,
mediator `70000005`, admin `70000006`. Step-by-step review: [docs/TESTING-GUIDE.md](docs/TESTING-GUIDE.md).

## Android app (preview)

See [android/README.md](android/README.md): run `.\start-dev.ps1 -Lan`, install `mcxus-preview.apk` on a phone on the same Wi-Fi.

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
  auth/                phone OTP, JWT, role checks
  api/                 HTTP routes and request/response schemas
  jobs.py              timer worker
  cli.py               make-admin, seed-demo, dev-token
backend/migrations/    Alembic (0001 money core; 0002 marketplace + PNG locations/categories seed in migrations/data)
backend/tests/         87 tests against real PostgreSQL
docs/                  architecture, decisions (ADRs), testing guide
```

## Backup and restore (sandbox)

```powershell
docker compose exec -T db pg_dump -U mcxus -Fc mcxus > backups\mcxus-$(Get-Date -f yyyyMMdd-HHmm).dump
docker compose exec -T db pg_restore -U mcxus -d mcxus --clean < backups\<file>.dump
```

## Licence

Apache-2.0 — see [LICENSE](LICENSE). Copyright 2026 Jerry Badu.
