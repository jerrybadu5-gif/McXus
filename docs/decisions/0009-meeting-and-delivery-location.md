# ADR 0009 — Meet-up and delivery location: GPS first, address second

Date: 14/10/2026 · Status: accepted (Jerry, after the M3 phone test: "delivery options should have current
location, or set gps location and have address as secondary identifier")

**Decision.** Every place where an item changes hands is a **GPS point** (5 decimals ≈ 1 m) plus an
**address or landmark** people recognise ("Eriku market gate, near BSP ATM"). PNG has few street addresses, so
the point is what phones navigate to and the landmark is what people ask for.

- **Listing:** the seller sets a meet-up / pickup point (*Use my location* or *Set on map*) and a landmark.
  Required in the app when the listing offers meet-up or pickup. Shown on the listing with **Directions**.
- **Order:** the buyer chooses how the item arrives. Seller delivers / courier → the buyer must give a point or
  an address. Meet-up / pickup → the seller's point is used unless the buyer suggests another. Buyer or seller
  can **Change place** until the order closes (logged as an order event). Shown on the order with Directions.
- **Chat:** either side can share a place (*+ → Share a location*). It is end-to-end encrypted like any message.
- **Directions** open the phone's own maps app (Google Maps, OsmAnd, Maps.me…) with a `geo:` link.
- Points must lie inside PNG (0–12°S, 140–160°E), checked on the phone and the server.

**How.** Location comes from Android's own LocationManager (no Google Play services; works on any Android 8+
phone). The map picker is osmdroid (Apache-2.0) with OpenStreetMap tiles, cached on the phone to save data.
Permission is asked only when the person taps *Use my location*. Reverse-geocoding fills a suggested landmark
when the phone can; people can always type their own.

**Privacy.** A listing's point is public, so the app tells sellers to pick a busy public place, not their home.
An order's delivery point is visible only to the buyer and seller (and later the assigned courier and a mediator
in a dispute). Chat locations never reach the server in readable form.

**Before launch.** OpenStreetMap's public tile servers are for light use only; switch to our own tile cache or
a commercial tile provider before scaling. Courier assignment (M4/M7) will reuse the order's delivery point.

API: `ListingIn.latitude/longitude/meetup_address` → `ListingOut.meetup {latitude, longitude, address}`;
`BuyIn.delivery {method, latitude, longitude, address}`; `OrderOut.delivery_method/_latitude/_longitude/_address`;
`POST /v1/orders/{id}/delivery-location`. Migration 0004.
