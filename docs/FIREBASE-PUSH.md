# Turning on push notifications (Firebase) — about 10 minutes

McXus works without this; messages arrive while the app is open. Push makes phones ring when McXus is closed.
Pushes carry **no message content** (ADR 0010).

1. Go to https://console.firebase.google.com → **Add project** → name it `mcxus` (Google Analytics: off).
2. In the project: **Add app → Android**. Package name: `pg.mcxus.app`. Download **google-services.json** and
   save it as `android/app/google-services.json`. (It is in `.gitignore` — do not commit it.)
3. **Project settings → Service accounts → Generate new private key**. Save the file as `secrets/firebase.json`
   in the McXus folder (also ignored by git; keep it secret — it can send pushes to your users).
4. Copy `backend/.env.example` to `backend/.env` if you have not, and uncomment
   `MCXUS_FCM_CREDENTIALS_FILE=/app/secrets/firebase.json`.
5. Restart the backend (VS Code task **McXus: start backend**) and rebuild the app (**Ctrl+Shift+B**).
6. Test: open McXus on the phone once (it registers), close it, and send it a message from another account —
   the phone shows a notification within a few seconds.

If no notification appears: check the API log for `Push notifications on (Firebase project …)`; on the phone,
allow notifications for McXus (Android 13+) and turn off battery optimisation for McXus on phones that
kill background apps aggressively (Tecno, Infinix, Itel, Xiaomi).
