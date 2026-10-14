# McXus Android app (0.4.0-m3.2)

Native Kotlin + Jetpack Compose (Material 3), McXus design: deep Pacific blue, kina gold, Plus Jakarta Sans.
Android 8.0+ (minSdk 26), targets Android 15 (API 35). **Sandbox: test Stars only.**

## What it does
- **Chats** — end-to-end encrypted one-to-one chats (OpenMLS, ADR 0008): start by phone number or **Chat** on a
  listing; listing cards and live escrow order cards inside the chat; unread counts; safety number (⋮ menu).
- **Groups** — up to 256 people; admins add/remove members and make other admins; leave anytime; sender names
  in colour; join/leave notices. Encrypted like 1:1 chats (MLS; ADR 0010).
- **Photos & voice notes** — + → Photo / Take a photo, or tap the microphone. Encrypted on the phone before upload.
- **Notifications** — when McXus is closed, if Firebase is set up (docs/FIREBASE-PUSH.md). The push itself carries
  no content; Me › Notifications can hide message text.
- **Discover** — feed of new listings with seller stories (posts, follows and Shorts videos arrive in M5).
- **Market** — search, categories, province filter, listing pages with photo pager, **Buy with Stars**
  (first buyer to pay gets it); the order card is sent to the seller in the encrypted chat.
- **Meet-up & delivery places** — GPS first (*Use my location* or *Set on map*, OpenStreetMap), landmark second;
  on listings, orders (change until closed) and shareable in chat; **Directions** open the phone's maps app.
- **Wallet** — balance (tap the eye to hide), limits, sandbox top-up, withdraw request, statement.
- **Orders / handover** — buyer sees QR + 6-digit PIN; seller accepts/rejects, enters the PIN; dispute, rate.
- **Me** — profile and store name, my listings, sell, server address, sign out.
Wallet and order screens block screenshots.

## Build, install and test from VS Code (USB debugging)

One time on the laptop: open the McXus folder in VS Code → **Terminal → Run Task… → Android: one-time setup
(Java 17 + Android SDK)** (or `powershell -ExecutionPolicy Bypass -File .\scripts\setup-android-windows.ps1`),
then restart VS Code. Phone: Developer options → **USB debugging ON**, plug in, tap **Allow**.

| Task (Terminal → Run Task…) | Same in PowerShell |
|---|---|
| McXus: start backend (Docker) | `.\start-dev.ps1 -Lan` |
| Android: check phone (USB) | `.\scripts\phone.ps1 check` |
| Android: install & open on phone (USB) — **Ctrl+Shift+B** | `.\scripts\phone.ps1 install` |
| Android: smoke test on phone (USB) | `.\scripts\phone.ps1 test` |
| Android: live log from phone | `.\scripts\phone.ps1 log` |
| Android: unit tests (laptop) | `cd android; .\gradlew.bat testDebugUnitTest lintDebug` |

**Server over the USB cable:** the install/test tasks run `adb reverse tcp:8000 tcp:8000`, so in the app the
server is simply `http://127.0.0.1:8000` while the cable is plugged in (no Wi-Fi needed). On Wi-Fi instead, use
the address `start-dev.ps1 -Lan` prints, e.g. `http://192.168.1.20:8000`.

The phone smoke test (`connectedDebugAndroidTest`) checks: the app opens; the encryption library works on the
phone's CPU; and — when the backend is running — two test accounts exchange an encrypted message through it.

Every test build is signed with the same debug key (`android/debug.keystore`, debug only), so updates install
over the old version. Plain HTTP is allowed only in debug builds; release builds are HTTPS only.

## Encryption library
`app/src/main/jniLibs/*/libmcxus_crypto.so` and `app/src/main/java/uniffi/` are built from `../crypto` (Rust,
OpenMLS). Rebuild only when `crypto/src` changes (Linux/WSL):
```
cd crypto
cargo ndk -t arm64-v8a -t armeabi-v7a -t x86_64 -P 26 -o ../android/app/src/main/jniLibs build --release
cargo build && cargo run --release --features bindgen --bin uniffi-bindgen -- generate \
  --library target/debug/libmcxus_crypto.so --language kotlin --out-dir ../android/app/src/main/java --no-format
```
`cargo build` also lets the laptop JVM tests (`CryptoBindingsTest`) run the real library; without it they are skipped.
Server/screenshot tests on the laptop: `MCXUS_E2E_SERVER=http://127.0.0.1:8000 ./gradlew testDebugUnitTest -Pe2e`.
