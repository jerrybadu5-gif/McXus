# ADR 0010 — Group chats, encrypted photos and voice notes, content-free push (M3.2)

Date: 15/10/2026 · Status: proposed for review (Jerry chose: messaging part 2 next; Firebase push with no content;
photos + voice notes; groups up to 256)

## Groups (MLS, up to 256 members)
- The creator's phone makes the MLS group alone (epoch 0); admins add people with one **Commit** (for current
  members) plus one **Welcome** (for the new ones), using one claimed KeyPackage per new person.
- **One change per epoch.** Each Commit carries the epoch it was made in; the server accepts it only if that is
  still the group's epoch, then counts up. A phone whose change was refused (`409 stale_epoch`) discards it,
  applies the change that won, and tries again. So every phone applies the same changes in the same order.
- Welcomes are stored before the Commit, so a new member joins first and ignores the older Commit.
- **Remove:** an admin's Commit takes the person out of the encryption; the server stops delivering to them at
  once. **Leave:** the server stops delivering immediately and posts a notice; the first admin phone to see it
  removes the person's keys. A group always keeps an admin (the longest member is promoted).
- The server sees the group name, who is in it, and who is admin — not the messages. Notices ("Pastor added
  Bob") are written by the server and contain only these facts.
- Up to 3 earlier epochs' keys are kept on the phone so a message sent just before a change still decrypts.
- Claims for groups: only admins, only for people not yet in the group; the 5-per-day-per-pair cap still applies.

## Photos and voice notes
- The phone seals each file with a fresh random AES-256-GCM key (Android's standard crypto library), uploads
  only the ciphertext, and puts the key, the file's SHA-256 and a ~1 KB blurry preview **inside the MLS message**.
  The server stores files it cannot read, in a private folder (never the public /media), for 30 days.
- Downloads are for members of that chat only; the phone checks the hash before decrypting.
- Photos: longest side 1280 px, JPEG quality 70 (≈100–200 KB). Voice: AAC mono 16 kHz, 24 kbit/s
  (≈30 KB per 10 s), up to 5 minutes. Max file 5 MB. Decrypted copies stay in app-private storage.

## Push (Firebase Cloud Messaging, content-free)
- A push contains only `{"t":"sync"}` — no text, no sender, no chat id. The phone wakes, fetches and decrypts,
  then shows the notification itself. Google learns only that this phone got *something*.
- Notifications are private on the lock screen ("New message"); Me › Notifications can hide the text everywhere.
- Server: service-account key in `secrets/firebase.json` (`MCXUS_FCM_CREDENTIALS_FILE`); without it pushes are
  off. App: `android/app/google-services.json`; without it the app builds and works, just without pushes.
  Setup: docs/FIREBASE-PUSH.md. Dead tokens are dropped automatically.

## Known limits
- One device per account holds a chat's keys. If the same account is opened on two devices (say a phone and
  the PC emulator), the device the person used most recently (opened, brought to the front or touched; not a
  background reconnect or push wake-up) is "active": new chats and groups are set up for it, and
  the server sends their Welcome only to that device (`recipient_device_id`, API level 5). The other device
  shows one notice ("This chat is set up on your other device…") instead of "could not be decrypted" for
  every message, and the composer says to reply on the other device. Real multi-device (each device a separate MLS member) is planned after the pilot.
- Notifications say only "McXus · New message" by default; showing who wrote and the text is opt-in
  (Me › Notifications).
- Reinstalling loses group keys: an admin removes and re-adds the person.
- Chat backup/restore is not in this release.
- Long-poll still delivers while the app is open; push only wakes it.
