# ADR 0002 — Double-entry ledger in PostgreSQL

Date: 14/10/2026 · Status: accepted (Jerry, F5)

**Decision.** Own double-entry ledger in PostgreSQL rather than an external ledger engine (e.g. TigerBeetle).
Postings are append-only (triggers), entries must balance (deferred constraint trigger), and each account has a
cached balance updated under row locks in the same transaction.

**Why.** <10k users in year one; one database is simpler to run, back up and audit on a single VPS. The single
`SYS:ESCROW` row is a lock hotspot under heavy load — if that ever matters, split escrow into per-order
sub-accounts or move to a dedicated ledger engine. Integrity report re-derives all balances to detect drift.
