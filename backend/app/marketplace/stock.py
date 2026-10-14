"""Stock reservation: the first buyer who PAYS gets the item (Jerry, 14/10/2026).

Creating an order does not reserve anything. Paying locks the listing row, checks stock and takes it.
A refund (seller rejects, auto-reject, cancellations) puts the stock back. A dispute does not, because the
goods may already have changed hands.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict
from app.models import Listing, Order


def _lock_listing(db: Session, order: Order) -> Listing:
    stmt = (
        select(Listing)
        .where(Listing.id == order.listing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalars(stmt).one()


def reserve(db: Session, order: Order) -> None:
    if order.listing_id is None or order.stock_reserved:
        return
    listing = _lock_listing(db, order)
    if listing.status != "active" or listing.quantity_available < order.quantity:
        raise Conflict("Sorry, someone else has just bought this item", code="sold_out")
    listing.quantity_available -= order.quantity
    if listing.quantity_available == 0:
        listing.status = "sold_out"
    order.stock_reserved = True


def release(db: Session, order: Order) -> None:
    if not order.stock_reserved:
        return
    listing = _lock_listing(db, order)
    listing.quantity_available += order.quantity
    if listing.status == "sold_out":
        listing.status = "active"
    order.stock_reserved = False
