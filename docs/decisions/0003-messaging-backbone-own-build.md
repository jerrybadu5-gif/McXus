# ADR 0003 — Messaging backbone: build our own (decided), on audited crypto libraries

Date: 14/10/2026 · Status: accepted by Jerry (C-1: c), against the recommendation of Matrix/Synapse

**Decision.** McXus will run its own messaging server (module M3).

**Guardrails (non-negotiable).** We never write our own cryptography. End-to-end encryption uses an audited,
permissively licensed library — candidates: OpenMLS (MIT, RFC 9420 MLS, good for groups) or vodozemac
(Apache-2.0, Olm/Megolm). The server stores only ciphertext, uses sealed-sender style addressing where
practical, and keeps minimal metadata. Choice between OpenMLS and vodozemac is made at the start of M3 after a
short spike on Android (Kotlin bindings, battery, low bandwidth).

**Risk.** Own build costs more time than adopting Matrix, and needs an external security review before launch.
