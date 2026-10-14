# ADR 0007 — Android preview in plain Kotlin, before chat

Date: 14/10/2026 · Status: accepted (Jerry: "developer mode android phone … primitive kotlin")

**Decision.** Ship an Android preview on top of M1+M2 now; chat joins the same app in M3. Native Kotlin with
plain Android views built in code — no XML layouts, no Compose, no AndroidX; platform HttpURLConnection and
org.json; only kotlinx-coroutines and ZXing core as dependencies. minSdk 26 (Android 8), target 35.

**Why.** Real-device feedback on PNG phones and networks early; small APK (≈1.7 MB) and few dependencies to audit;
easy to read for a two-person team. Compose or AndroidX can be adopted later screen by screen if needed.

**Security.** Screenshots blocked on wallet and order screens (FLAG_SECURE). Token in app-private storage, backups
disabled. Plain HTTP only in debug builds (LAN testing); release builds HTTPS only. Handover PINs kept in memory.
Before launch: move the token to Android Keystore-backed storage and add certificate pinning.
