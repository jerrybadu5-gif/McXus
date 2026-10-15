# McXus staff console

Web console for McXus staff: disputes, deposits and payouts, reported listings, people (verification level,
staff role, freeze), money reports and the staff activity log. Each role sees only its own parts; the API
enforces the same rules (ADR 0011).

## Run it

- With Docker (normal): `docker compose up -d` from the repo root, then open http://localhost:8080
  (VS Code task **McXus: open staff console**). nginx serves the app and forwards `/v1` to the API.
- For development: `npm install`, then `npm run dev` (http://localhost:5173, forwards `/v1` to
  http://127.0.0.1:8000; set `MCXUS_API` to use another API).

Sign in with a staff phone number. In sandbox mode the code is filled in. Demo staff (after `seed-demo`):
mediator 70000005, compliance 70000009, finance 70000003 / 70000004, moderator 70000007, KYC 70000010,
support 70000011, admin 70000006. Make someone staff: People → Change staff role (admin), or
`python -m app.cli make-admin <phone>`.

## Checks

```
npm run typecheck
npm test          # money maths, deadlines, the stage track
npm run build
```

## Notes

- Money arrives from the API as decimal strings and is never turned into floating-point numbers for
  arithmetic (`src/lib/utils.ts`).
- The sign-in token is kept in sessionStorage and is gone when the tab closes.
- Keep port 8080 on 127.0.0.1 (as in docker-compose.yml) or behind a VPN; it is for staff only.
