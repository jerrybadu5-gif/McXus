# M1 review and test guide (for Jerry)

Nothing is pushed to GitHub until you have run this and said it passes.

## 1. Automatic checks (5 minutes)

```powershell
cd $HOME\Documents\Developer\mcxus
.\run-tests.ps1
```
Expect `55 passed` and "All checks passed". Then:
```powershell
.\start-dev.ps1
python scripts\smoke_test.py
```
Expect every line `PASS`.

## 2. Hands-on in the API docs (20 minutes)

Open http://localhost:8000/docs. Get tokens:
```powershell
docker compose exec api python -m app.cli dev-token 70000001   # buyer
docker compose exec api python -m app.cli dev-token 70000002   # seller
```
Click **Authorize**, paste a token, and switch tokens as needed. For money actions, put any unique text in
`Idempotency-Key` (e.g. `test-1`, `test-2`).

| # | Try this | You should see |
|---|---|---|
| 1 | Buyer: `POST /v1/wallet/sandbox-topup` `{"amount":"500.00"}` | balance `"500.00"` |
| 2 | Repeat #1 with the **same** Idempotency-Key | same answer, balance still 500 |
| 3 | Seller: `GET /v1/me`, copy `id`. Buyer: `POST /v1/orders` with that `seller_id`, amount `200.00` | status `CREATED` |
| 4 | Buyer: `POST /v1/orders/{id}/pay` | status `FUNDED`, a 6-digit `handover_pin`; wallet 300 |
| 5 | Seller: `/accept`, then `/handover` with a wrong PIN | `pin_invalid` |
| 6 | Seller: `/handover` with the right PIN | `RELEASED`, `seller_paid` `"194.00"`, `fee_charged` `"6.00"` |
| 7 | New order + pay, then seller `/reject` (or wait 20 minutes) | `SELLER_REJECTED` / `AUTO_REJECTED`; buyer refunded the full 200; no fee |
| 7b | New order + pay + seller `/accept`; wait 25+ minutes; seller `/cancel` | `SELLER_CANCELLED`; buyer gets 200 + 5; seller pays the K10 fee (owed from next sale if wallet is short) |
| 8 | New order + pay; buyer `/cancel` | `CANCELLED`; buyer refunded 190; seller +5 |
| 9 | New order + pay + accept + dispatch; buyer `/dispute`; mediator token (`70000005`) `POST /v1/admin/disputes/{id}/resolve` `{"buyer_refund":"50.00","note":"Partial damage"}` | `RESOLVED`; buyer +50; seller +145.50 |
| 10 | Finance A (`70000003`) `POST /v1/admin/deposits`; approve it as Finance A | `maker_checker` refused; approve as Finance B (`70000004`) works |
| 11 | Finance: `GET /v1/admin/reports/integrity` | `"ok": true` |
| 12 | Buyer token on any `/v1/admin/...` route | 403 |

## 3. Penalty rules (confirmed by Jerry 14/10/2026)

Goal: sellers sell to the first buyer who pays, and buyers only pay when they mean to buy.

1. **Buyer cancels after paying** (before dispatch): buyer pays the 5% fee (minimum K2), split 50/50
   seller/platform. Cancelling before paying is free. After dispatch: dispute only.
2. **Seller rejects within 20 minutes, or lets the 20 minutes pass**: no penalty; buyer refunded in full.
3. **Seller cancels after accepting**: free within 25 minutes of payment; after that the seller pays the 5% fee
   (buyer gets half, platform half). If the seller's wallet is short, the rest is taken from their next sale.
4. **Delivered and confirmed** (PIN, buyer confirms, or 7 days after dispatch): seller pays the 3% escrow fee.
5. Wrong handover PIN 5 times locks it; the buyer re-issues a new PIN.

All values are settings in `backend/.env` (`MCXUS_SELLER_ACCEPT_MINUTES`, `MCXUS_SELLER_PENALTY_FREE_MINUTES`,
`MCXUS_CANCEL_FEE_*`, `MCXUS_ESCROW_FEE_*`).

## 4. When it passes

Tell me "M1 passed" and I will push it to `github.com/jerrybadu5-gif/mcxus` (public) on a `feat/m1-money-core`
branch with a pull request for you to merge, then start M2 (marketplace).
