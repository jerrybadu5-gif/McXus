# Review and test guide (for Jerry)

M1 (money core) passed on 14/10/2026. **M2 (marketplace) checks are in section 5.**

# M1 money core

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

Done for M1 (PR #1). For M2: tell me "M2 passed" and I will push `feat/m2-marketplace` and open PR #2.

## 5. M2 marketplace checks (20 minutes)

`.\run-tests.ps1` should now show **87 passed**; `python scripts\smoke_test.py` adds two marketplace lines.
New demo users: moderator `70000007`, second buyer `70000008`. Run `.\start-dev.ps1` again first, which applies
the new database migration (your M1 test data is kept).

| # | Try this | You should see |
|---|---|---|
| M1 | `GET /v1/locations` then `GET /v1/locations?parent_id=<Morobe id>` then the Lae id | 22 provinces; Morobe districts; Lae suburbs (Eriku, Top Town…) |
| M2 | `GET /v1/categories` | category tree; no firearms/alcohol/betel nut |
| M3 | Seller: `POST /v1/listings` with title `Fresh buai` | `prohibited_content` |
| M4 | Seller: `POST /v1/listings` a real item (quantity 1, a leaf category id, Morobe + Lae) | `active`, seller badge `new_seller` |
| M5 | Seller: `POST /v1/listings/{id}/photos` with a phone photo | 1280 px wide/high; open `thumb_url` in the browser (http://localhost:8000 + url) |
| M6 | No token: `GET /v1/listings?q=` + first letters of your title | your listing (browsing is public) |
| M7 | Second buyer (`70000008`) tops up K500 first. Buyer (`70000001`) and second buyer: both `POST /v1/listings/{id}/buy` | two `CREATED` orders |
| M8 | Buyer pays first; second buyer pays | first: `FUNDED`, listing `sold_out`; second: `sold_out` error, wallet unchanged |
| M9 | Seller `/reject`s the first order | listing back to `active`; second buyer can now pay |
| M10 | Complete an order (accept + handover PIN), buyer `POST /v1/orders/{id}/review` 5 stars | `GET /v1/sellers/{id}` shows rating 5.0, 1 completed sale |
| M11 | Three different users `POST /v1/listings/{id}/report` | after the third, listing hidden from search (`under_review`) |
| M12 | Moderator (`70000007`): `GET /v1/mod/reports`, then `POST /v1/mod/listings/{id}/decision` `{"action":"restore"}` | listing back; reports cleared |
| M13 | Seller `PUT /v1/me/profile` with a `store_name` | listings and seller page show the store name |

### Please confirm

1. **District list** (`backend/migrations/data/png_locations.json`) is the 89-district set from my knowledge;
   check against the official list (2022 boundaries added new electorates) and send corrections.
2. **Blocked words** (`backend/app/marketplace/moderation.py`): add any local terms you want blocked.
3. **Trust badges:** new seller until 3 completed sales; bronze 40+, silver 60+, gold 80+; "verified store"
   needs tier 3 and 60+; "caution" below 40. A lost dispute costs 10 points, a late seller cancellation 5.
