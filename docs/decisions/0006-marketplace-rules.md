# ADR 0006 — Marketplace rules (M2)

Date: 14/10/2026 · Status: accepted (Jerry, M2-1 … M2-6)

- **First buyer who pays gets the item.** Starting an order reserves nothing; paying locks the listing row and
  takes the stock. Refunds (seller rejects, auto-reject, cancellations) put it back; disputes do not.
- **Photos:** up to 5 per listing; resized to 1280 px (thumbnail 320 px), re-encoded as JPEG, all metadata removed
  (phone photos carry GPS). Stored in a local folder/volume now; object storage (S3/SeaweedFS) + CDN before launch.
- **Locations:** 22 provinces, 89 districts, suburbs for Port Moresby (attached to NCD) and Lae (attached to Lae
  district). Seed data in `backend/migrations/data/png_locations.json` — verify against NSO/PNGEC lists.
- **Search:** PostgreSQL full-text search with the `simple` dictionary (works for English, Tok Pisin and place
  names), prefix matching for partly typed words, filters for category (parent includes children), location,
  price, condition, seller. Upgrade path: Meilisearch if volume or typo-tolerance demands it.
- **Ratings:** only the buyer of a completed order (RELEASED/RESOLVED), once, 1–5 stars + optional comment.
- **Trust score v1:** Bayesian rating + completed sales + verification, minus disputes lost and late seller
  cancellations; public badge (new seller, bronze, silver, gold, verified store, caution), raw score staff-only.
- **Prohibited items:** banned categories + whole-word keyword block on titles, descriptions and review comments +
  "Report listing"; three distinct open reports hide a listing until a moderator removes or restores it.
