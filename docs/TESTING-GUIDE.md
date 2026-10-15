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

## 6. Android preview on your phone (30 minutes)

Install: see `android/README.md` (start the laptop with `.\start-dev.ps1 -Lan`, same Wi-Fi, install
`mcxus-preview.apk`). Use two phones if you have them, or sign out and in to switch between buyer and seller.

| # | On the phone | You should see |
|---|---|---|
| P1 | Enter the server address, phone `70000002`, **Send code**, **Sign in** | code filled in (sandbox); Market tab |
| P2 | **Sell**: title, category, price, Morobe → Lae → Eriku, **Save and add photos**, **Take photo** | listing page with your photo |
| P3 | Try to screenshot the **Wallet** tab | Android refuses ("can't take screenshot") |
| P4 | Sign out; sign in as buyer `70000001`; **Wallet** → top up 500 | balance K500.00 |
| P5 | **Market**: type the first letters of your item, **Search**, open it, **Buy with Stars** | order page: QR code + 6-digit PIN |
| P6 | Sign in as seller `70000002` → **Orders → Selling** → open the order → **Accept** | "Accepted" |
| P7 | Type the buyer's PIN → **Confirm handover** | "Completed — Stars paid to the seller"; seller Wallet +K(price − 3%) |
| P8 | Buyer: open the order → **Rate the seller** 5 stars | seller page shows ★ 5.0 |
| P9 | Turn Wi-Fi off and tap Search | a clear "Cannot reach the McXus server" message, no crash |
| P10 | Second buyer `70000008` tries to buy a sold-out item | "Sold out" — cannot pay |

Please tell me: phone model and Android version, anything slow, confusing words, and screenshots of problems
(from screens that allow them).

## 7. M3 encrypted chat + new app, from VS Code with USB (40 minutes)

**Setup (once):** VS Code → Terminal → Run Task… → **Android: one-time setup (Java 17 + Android SDK)**, restart
VS Code. Phone: Developer options → USB debugging ON → plug in → tap **Allow**.

| # | Do | You should see |
|---|---|---|
| C1 | Task **McXus: start backend (Docker)** | API docs open in the browser |
| C2 | Task **Android: check phone (USB)** | "Connected: <model>, Android <n>" and "Backend is running" |
| C3 | Task **Android: smoke test on phone (USB)** (Enter = `usb`) | `PhoneSmokeTest` 3 tests passed (app opens, encryption on the phone, encrypted chat via the server) |
| C4 | **Ctrl+Shift+B** (install & open) | McXus opens on the phone; server `http://127.0.0.1:8000` |
| C5 | Sign in as seller `70000002`, Market → **Sell** → add a listing with a photo | your listing page |
| C6 | Me → Sign out; sign in as buyer `70000001`; Wallet → **Top up** 500 | K500.00 |
| C7 | Market → open the listing → **Chat** | chat opens, listing card is the first message, "encrypted" under the name |
| C8 | Type "Moning! Still available?" → send | blue bubble with time and ✓ |
| C9 | Back → listing → **Buy with Stars** → Pay | order screen with QR + PIN; the chat shows a gold **K… in escrow** card |
| C10 | Sign in as the seller on a 2nd phone (or sign out/in) → **Chats** | the chat with unread badge; both messages readable |
| C11 | Seller: tap the escrow card → **Accept order**, then type the buyer's PIN → **Confirm handover** | "Completed — Stars paid to the seller" |
| C12 | In the chat: ⋮ → **Verify encryption** on both phones | the same 60-digit safety number |
| C13 | Task **Android: live log from phone** while chatting | no red errors (`McXusChat` lines only) |
| C14 | Turn off the laptop's backend, send a message | a clear "Can't reach the McXus server" message; the list shows "Connecting…" |

Note: with one phone, signing out and in switches accounts on the same phone (each account keeps its own keys).
Tell me: phone model, anything slow or confusing, and how the design feels compared to WhatsApp/Telegram.

### 7b. Meet-up and delivery location (ADR 0009)

| # | Do | You should see |
|---|---|---|
| L1 | Seller: **Sell** → tick Meet-up → **Use my location** (allow location) | "GPS point set" with coordinates; a landmark may be filled in |
| L2 | **Set on map** → drag the map so the pin is on a public spot → **Use this point**; type a landmark | coordinates change; landmark kept |
| L3 | Post, open the listing | "Meet-up / pickup point" card; **Directions** opens your maps app at that spot |
| L4 | Buyer: **Buy with Stars** → choose **Courier** (or Seller delivers) and tap Pay without a place | "Set where to deliver…" — cannot pay yet |
| L5 | Set the delivery place (your location or map + landmark) → Pay | order screen shows "Courier delivers to …" with Directions |
| L6 | Seller: open the order → **Change place** → new landmark → Save | buyer sees the new place after refresh |
| L7 | In the chat: **+ → Share a location** → Send | a "Meet / deliver here" card with Directions on both phones |
| L8 | Location turned off on the phone, tap **Use my location** | a clear message to turn Location on; **Set on map** still works |

## 8. M3.2 groups, photos, voice notes, notifications (40 minutes)

Use two phones, or one phone plus the laptop emulator. Push needs the Firebase setup in `docs/FIREBASE-PUSH.md`
(G9–G10 only); everything else works without it.

| # | Do | You should see |
|---|---|---|
| G1 | Chats → gold button → **New group** → name it, tick two people (or add by number) → **Create group** | the group opens; "You added …"; header shows "3 members · encrypted" |
| G2 | On the other phones | the group appears; they can send and read; incoming bubbles show the sender's name in colour |
| G3 | **+ → Photo from gallery** (type a caption first if you like) | blurry preview at once, sharp photo after a second; tap opens full screen |
| G4 | **+ → Take a photo** | same, from the camera |
| G5 | Tap the **microphone**, speak, tap send (or ✕ to cancel) | a voice bubble with length; others tap ▶ to play |
| G6 | Group info (tap the group name) → **Add people** | new person joins and can read new messages (not older ones) |
| G7 | Group info → tap a member → **Remove from group** | they see "You were removed"; they no longer get messages |
| G8 | A member taps **Leave group** | "<name> left"; the admin's phone removes their keys automatically |
| G9 | Close McXus on phone A; send it a message from phone B | notification on A within seconds: "McXus · New message" |
| G10 | Me → **Notifications** → Show text, repeat G9 | notification shows the name and text (lock screen still "New message") |
| G11 | Try to send a 10-minute voice note | recording stops at 5 minutes |
| G12 | Demo buyer on the emulator and the phone. Tap the phone (it is now the device in use), switch the phone to the seller, make a group with the demo buyer and send a message | the emulator shows one grey note "This chat is set up on your other device…" and "Read and reply… on your other device" instead of the message box; the seller sees no grey note; switching the phone back to the buyer shows the message |
| G13 | Lock the phone or leave McXus, then get a message | notification says "McXus · New message" only (Me › Notifications › Show text turns on name and text) |

## 9. M4 disputes and the staff console (45 minutes)

Rebuild first: task **McXus: start backend** (it now also starts the staff console), then reinstall the app
(Ctrl+Shift+B). Optional sample cases: task **McXus: sample disputes (sandbox)**.

Staff console: task **McXus: open staff console** or http://localhost:8080. Sign in with a demo staff number; the
sandbox fills in the code. Mediator 70000005 · compliance 70000009 · finance 70000003 and 70000004 · moderator
70000007 · KYC 70000010 · support 70000011 · admin 70000006.

| # | Do | You should see |
|---|---|---|
| D1 | App, demo buyer: buy something from the demo seller, pay; seller accepts. Buyer: order → **Problem with the item? Open a dispute**, write what went wrong | the dispute screen: stage "Agree", the 3-day deadline, your statement |
| D2 | Buyer: **Add a photo** (camera or gallery) | the photo appears under your statements; the seller sees it too |
| D3 | Seller: Me → **Disputes** → the case → **Make an offer** (e.g. Half) | buyer sees "The seller offered… waiting for you" with Reject / Accept |
| D4 | Buyer: **Accept** | "Closed": buyer got back the offer, seller the rest less 3%; check both wallets |
| D5 | New dispute; buyer taps **Ask a mediator now** | stage "Mediator", due in 5 working days; console: Disputes shows it under "Need a mediator" |
| D6 | Console as mediator: open it → **Take the case** → **Decide the refund** → Half, write a reason → Decide | the case moves to "Decided"; in the app both see the decision with **Accept** / **Appeal (once)** |
| D7 | App: seller taps **Appeal (once)** with a reason | stage "Appeal"; console as mediator: no decide button (the mediator can't hear the appeal) |
| D8 | Console as compliance: Disputes → Appeals → **Make the final decision** | "Resolved (appeal decision)"; wallets updated; Money reports → "Every entry balances" |
| D9 | New dispute, mediator decides, both parties tap **Accept the decision** | closes at once without waiting 3 days |
| D10 | Console as finance A: **Record a bank deposit** for the demo buyer; then as finance B approve it | A can't approve their own; after B approves, the buyer's wallet goes up |
| D11 | Console as admin: People → find the demo seller → **Change verification**, **Freeze account** (compliance or admin) | the seller can't use the app while frozen; Staff activity lists both actions with your name |
| D12 | Console on a phone-size window | the menu moves to the top; lists and cases stack |

### Please confirm

- Are the three windows right: **3 days** to agree, **5 PNG working days** for the mediator, **3 days** to appeal?
- Should the senior decision be **compliance or admin** (as built), or a separate "senior mediator" role?
