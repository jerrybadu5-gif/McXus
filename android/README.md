# McXus Android preview (0.1.0-preview)

Native Kotlin, plain Android views built in code (no XML layouts, no UI framework). Libraries: kotlinx-coroutines
and ZXing core (QR code) only. Android 8.0+ (minSdk 26), targets Android 15 (API 35). **Sandbox: test Stars only.**

## What it does
Sign in with a phone number (sandbox shows the code on screen) · Market: search, category and province filters,
listing pages with photos and seller badge · Buy with Stars (first buyer to pay gets it) · Orders as buyer or seller:
pay, accept/reject, dispatch, handover by PIN (buyer sees a QR code + PIN), confirm receipt, cancel, dispute, rate ·
Sell: create a listing with province/district/suburb and add photos from the camera or gallery · Wallet: balance,
limits, sandbox top-up, statement · Me: profile and store name, my listings, server address.
Wallet and order screens block screenshots.

Not yet: chat (M3), scanning the QR with the camera (seller types the PIN for now), Tok Pisin text, iOS.

## Install on your phone (developer mode)

1. Laptop: `.\start-dev.ps1 -Lan` — it prints the server address, e.g. `http://192.168.1.20:8000`.
   If Windows Firewall asks about Docker, allow **Private networks** only.
2. Phone and laptop on the **same Wi-Fi**.
3. Install the APK, either:
   - USB: phone in developer mode with **USB debugging** on, then on the laptop
     `adb install -r mcxus-preview.apk` (adb comes with Android Studio's platform-tools), or
   - copy `mcxus-preview.apk` to the phone (or download it from the chat) and open it; allow "Install unknown apps"
     for that one app when Android asks.
4. Open McXus, enter the server address from step 1, a demo phone number (buyer `70000001`, seller `70000002`,
   second buyer `70000008`), tap **Send code** (sandbox fills it in) and **Sign in**.

Updates install over the old version because every test build is signed with the same debug key
(`android/debug.keystore`, debug only — never used for a Play Store release).

## Build it yourself (optional)
Android Studio (Koala or newer) → Open the `android` folder → Run. Or command line with JDK 17+:
`.\gradlew assembleDebug` → `app\build\outputs\apk\debug\app-debug.apk`. Tests: `.\gradlew testDebugUnitTest lintDebug`.

Plain HTTP is allowed only in debug builds (to reach the laptop on Wi-Fi); release builds are HTTPS only.
