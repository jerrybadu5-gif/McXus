# ADR 0008 — Encrypted one-to-one chat with OpenMLS (M3)

Date: 14/10/2026 · Status: proposed for review (Jerry approved OpenMLS, 1:1 + chat-with-seller first, 30-day server
retention, Jetpack Compose)

**Decision.** Chat uses MLS (RFC 9420) through **OpenMLS 0.8.2** (MIT), ciphersuite
`MLS_128_DHKEMX25519_AES128GCM_SHA256_Ed25519`. A small Rust crate (`crypto/`) wraps it and exposes a
Kotlin API with UniFFI; it is compiled for phones (`arm64-v8a`, `armeabi-v7a`, `x86_64`) and committed as `.so`
files so the app builds without Rust. We do not write any cryptography ourselves (ADR 0003).

**How a chat starts.**
1. Each phone registers a device and keeps ≥ 10 one-time **KeyPackages** on the server (uploads 20 at a time).
2. A opens a chat with B (by phone number, or **Chat** on a listing). A claims one of B's KeyPackages
   (`SELECT … FOR UPDATE SKIP LOCKED`, so two claims never get the same one), creates the MLS group locally and
   uploads the **Welcome**. The group id is `mcxus:<conversation>:<random>`.
   Claims are only allowed for a chat that exists and is not yet set up, at most 5 a day per pair, so nobody
   can drain another person's KeyPackages (which would stop others from starting chats with them).
3. Only the first Welcome is accepted (`UPDATE … WHERE mls_ready_by IS NULL`). If both phones start at the same
   moment, the slower one gets `409 already_initialised`, waits, and joins from the winner's Welcome (tested).
4. Messages are MLS application messages. The server stores ciphertext only, delivers it with a long-poll
   (`GET /v1/messages/sync?wait=25`, ~1 s latency, no push service needed yet) and deletes it after **30 days**.
5. Each phone checks that the MLS sender identity (`user:<id>`) matches the server's sender before showing a message.

**What the server can see.** Who talks to whom and when, message sizes, and the listing a chat was opened from.
It cannot read messages, listing/order cards shared in chat, or the safety number.

**On the phone.** Keys and group state: app-private file `mls-<user>.bin` (written atomically). Decrypted
messages: app-private SQLite `chat-<user>.db`. Android backups are off. Payloads are small JSON:
`text`, `listing` card, `order` card (live escrow status is fetched from the order API, not trusted from chat).

**Known limits in M3 (accepted for the pilot).**
- One active device per user. Registering a new device retires the old unused KeyPackages.
- Reinstalling the app or clearing its data loses the keys: old chats cannot be read, and a chat that phone
  started cannot continue (the app explains; the other person starts a new chat). Encrypted backup comes later.
- KeyPackages are trust-on-first-use. Safety numbers (60 digits, chat menu ⋮) let people verify in person;
  a "verified" badge and key-change warnings come later.
- Long-poll holds one server thread per online phone: fine for the pilot (hundreds of users); move to
  WebSockets/async + push (FCM or UnifiedPush) before scale.
- External security review of the crypto wrapper and protocol flow before launch (ADR 0003).
