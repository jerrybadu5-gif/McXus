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
| 7 | New order + pay, wait 21 minutes (or leave it) | worker sets `AUTO_REJECTED`; buyer gets 200 + 5 back; seller's `penalties_owed` 10 (if the seller's wallet was empty) |
| 8 | New order + pay; buyer `/cancel` | `CANCELLED`; buyer refunded 190; seller +5 |
| 9 | New order + pay + accept + dispatch; buyer `/dispute`; mediator token (`70000005`) `POST /v1/admin/disputes/{id}/resolve` `{"buyer_refund":"50.00","note":"Partial damage"}` | `RESOLVED`; buyer +50; seller +145.50 |
| 10 | Finance A (`70000003`) `POST /v1/admin/deposits`; approve it as Finance A | `maker_checker` refused; approve as Finance B (`70000004`) works |
| 11 | Finance: `GET /v1/admin/reports/integrity` | `"ok": true` |
| 12 | Buyer token on any `/v1/admin/...` route | 403 |

## 3. Please confirm or change these rules

These are implemented as config/code and are easy to change:

1. **Seller misses the 20-minute window or rejects**: buyer refunded in full **plus half** the 5% cancellation
   fee; the other half goes to the platform; the seller pays the whole fee, and any shortfall is taken from
   their next sale. *(My reading of your C7 answer.)*
2. **Buyer cancels after paying** (before dispatch): buyer pays the 5% fee (minimum K2), split 50/50 seller/platform.
   After dispatch the buyer cannot cancel; they open a dispute.
3. **Seller cancels after accepting**: treated like a rejection (rule 1).
4. Auto-release counts 7 days from **dispatch**.
5. Wrong handover PIN 5 times locks it; the buyer re-issues a new PIN in the app.

## 4. When it passes

Tell me "M1 passed" and I will push it to `github.com/jerrybadu5-gif/mcxus` (public) on a `feat/m1-money-core`
branch with a pull request for you to merge, then start M2 (marketplace).
