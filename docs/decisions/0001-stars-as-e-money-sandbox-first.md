# ADR 0001 — Stars are e-money; run in sandbox until a licensed issuer partners

Date: 14/10/2026 · Status: accepted (Jerry, Round 2: F1, F2, C4)

**Context.** Stars bought with kina and cashed back to kina are a retail payment instrument. The BPNG Directive
on Payment Instruments requires a Central Bank licence to issue (4.1), customer funds in a trust account at a
licensed commercial bank (10.3–10.4), monthly trust reconciliation (12.1(c)), and no interest or lending from the
float (11.1). Money-transfer services register with FASU and run an AML/CTF programme.

**Decision.** 1 Star = 1 PGK. McXus is the technology and marketplace layer; a licensed issuer (bank or
licensed e-money issuer) will hold the trust account. Until a partner is signed, the system runs in sandbox mode
(test Stars, self-service top-up) and refuses to start in production with sandbox on. No free P2P transfers;
Stars move through orders only (gifting for T2+ comes in M6).

**Consequences.** Ledger has a trust-bank asset account and a reconciliation report from day one. Interest-bearing
or savings features are excluded.
