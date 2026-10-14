"""Escrow orders: a state machine where every money step is one balanced ledger entry.

    CREATED --pay--> FUNDED --accept (within 20 min)--> ACCEPTED --dispatch--> DISPATCHED
       |               |  \\--reject---------> SELLER_REJECTED   |    |                |
       |               |   \\--20 min passed-> AUTO_REJECTED     |    |                |
     cancel          cancel (fee)                       cancel (fee) |   handover PIN / buyer confirms /
       v               v                                 seller cancels   7 days after dispatch
    CANCELLED       CANCELLED                       -> SELLER_CANCELLED          v
                                                                              RELEASED
    ACCEPTED or DISPATCHED --dispute--> DISPUTED --mediator--> RESOLVED (release / refund / split)

Money rules (Round 2, confirmed 14/10/2026):
- No free cancellation once paid. Buyer cancels before dispatch: buyer pays the cancellation fee, shared
  between the seller and the platform.
- Seller rejects, lets the 20-minute window pass, or cancels after accepting: buyer gets a full refund plus a
  share of the cancellation fee; the seller pays the fee from their wallet, and any shortfall is recorded as
  owed and taken from the seller's next sale.
- On release the seller pays the escrow fee; owed penalties are recovered first.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import clock, kyc
from app.config import get_settings
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.escrow.fees import cancel_fee, escrow_fee, split_cancel_fee
from app.ledger.service import (
    ESCROW,
    FEE_REVENUE,
    Line,
    credit,
    debit,
    order_escrow_balance,
    post_entry,
    system_account_id,
    user_account,
)
from app.models import Dispute, Order, OrderEvent, User
from app.money import ZERO

TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"FUNDED", "CANCELLED"},
    "FUNDED": {"ACCEPTED", "SELLER_REJECTED", "AUTO_REJECTED", "CANCELLED"},
    "ACCEPTED": {"DISPATCHED", "RELEASED", "DISPUTED", "CANCELLED", "SELLER_CANCELLED"},
    "DISPATCHED": {"RELEASED", "DISPUTED"},
    "DISPUTED": {"RESOLVED"},
}
OPEN_FOR_HANDOVER = ("ACCEPTED", "DISPATCHED")


# ---------- helpers ----------


def get_order(db: Session, order_id: uuid.UUID, *, lock: bool = False) -> Order:
    stmt = select(Order).where(Order.id == order_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    order = db.scalars(stmt).first()
    if order is None:
        raise NotFound("Order not found")
    return order


def get_order_for(db: Session, user: User, order_id: uuid.UUID, *, lock: bool = False) -> Order:
    """Load an order the user is a party to (staff with a review role may see any order)."""
    order = get_order(db, order_id, lock=lock)
    if user.id not in (order.buyer_id, order.seller_id) and user.role not in ("mediator", "support", "admin"):
        raise NotFound("Order not found")
    return order


def _transition(
    db: Session, order: Order, to: str, actor_id: uuid.UUID | None, reason: str = "", **data: object
) -> None:
    if to not in TRANSITIONS.get(order.status, set()):
        raise Conflict(f"This order is {order.status} and cannot become {to}", code="invalid_transition")
    db.add(
        OrderEvent(
            order_id=order.id,
            from_status=order.status,
            to_status=to,
            actor_id=actor_id,
            reason=reason,
            data={k: str(v) for k, v in data.items()},
            created_at=clock.now(),
        )
    )
    order.status = to


def _pin_hash(order_id: uuid.UUID, pin: str) -> str:
    key = get_settings().otp_secret.encode()
    return hmac.new(key, f"order:{order_id}:{pin}".encode(), hashlib.sha256).hexdigest()


def _new_pin(order: Order) -> str:
    pin = f"{secrets.randbelow(1_000_000):06d}"
    order.handover_pin_hash = _pin_hash(order.id, pin)
    order.handover_attempts = 0
    return pin


def _require_party(order: Order, user: User, party: str) -> None:
    expected = order.buyer_id if party == "buyer" else order.seller_id
    if user.id != expected:
        raise Forbidden(f"Only the {party} can do this")


def _assert_escrow_intact(db: Session, order: Order) -> None:
    held = order_escrow_balance(db, order.id)
    if held != order.amount:
        raise AppError(
            f"Escrow for this order holds K{held}, expected K{order.amount}. Refer to finance.", code="escrow_mismatch"
        )


# ---------- buyer and seller actions ----------


def create_order(db: Session, buyer: User, seller_id: uuid.UUID, title: str, amount: Decimal) -> Order:
    kyc.require(buyer.kyc_tier, "buy")
    seller = db.get(User, seller_id)
    if seller is None or seller.status != "active":
        raise NotFound("Seller not found")
    if seller.id == buyer.id:
        raise AppError("You cannot buy from yourself", code="self_purchase")
    if not kyc.TIERS[seller.kyc_tier].can_sell:
        raise Conflict("This seller is not verified to sell yet", code="seller_not_verified")
    order = Order(id=uuid.uuid4(), buyer_id=buyer.id, seller_id=seller.id, title=title, amount=amount)
    db.add(order)
    db.flush()
    db.add(
        OrderEvent(
            order_id=order.id, from_status=None, to_status="CREATED", actor_id=buyer.id, created_at=clock.now(), data={}
        )
    )
    return order


def pay(db: Session, buyer: User, order_id: uuid.UUID) -> tuple[Order, str]:
    """Move Stars from the buyer's wallet into escrow. Returns the order and the buyer's handover PIN."""
    order = get_order(db, order_id, lock=True)
    _require_party(order, buyer, "buyer")
    kyc.require(buyer.kyc_tier, "buy")
    now = clock.now()
    _transition(db, order, "FUNDED", buyer.id)
    wallet = user_account(db, buyer.id, "wallet")
    post_entry(
        db,
        "order_fund",
        [
            debit(wallet.id, order.amount, f"Paid into escrow: {order.title}"),
            credit(system_account_id(db, ESCROW), order.amount, f"Escrow: {order.title}"),
        ],
        order_id=order.id,
        created_by=buyer.id,
    )
    order.funded_at = now
    order.accept_deadline = now + timedelta(minutes=get_settings().seller_accept_minutes)
    return order, _new_pin(order)


def accept(db: Session, seller: User, order_id: uuid.UUID) -> Order:
    order = get_order(db, order_id, lock=True)
    _require_party(order, seller, "seller")
    now = clock.now()
    if order.status == "FUNDED" and order.accept_deadline and now >= order.accept_deadline:
        raise Conflict("The acceptance window has passed; the buyer will be refunded", code="accept_window_passed")
    _transition(db, order, "ACCEPTED", seller.id)
    order.accepted_at = now
    return order


def reject(db: Session, seller: User, order_id: uuid.UUID, reason: str) -> Order:
    order = get_order(db, order_id, lock=True)
    _require_party(order, seller, "seller")
    if order.status != "FUNDED":
        raise Conflict("Only a paid order that you have not accepted yet can be rejected", code="invalid_transition")
    _seller_fault_refund(db, order, "SELLER_REJECTED", seller.id, reason or "Seller rejected the order")
    return order


def cancel(db: Session, user: User, order_id: uuid.UUID, reason: str) -> Order:
    order = get_order(db, order_id, lock=True)
    if user.id == order.buyer_id:
        if order.status == "CREATED":
            _transition(db, order, "CANCELLED", user.id, reason or "Cancelled before payment")
            order.closed_at = clock.now()
        elif order.status in ("FUNDED", "ACCEPTED"):
            _buyer_cancel_with_fee(db, order, user.id, reason)
        else:
            raise Conflict(
                "This order can no longer be cancelled. Open a dispute if there is a problem.",
                code="invalid_transition",
            )
    elif user.id == order.seller_id:
        if order.status == "CREATED":
            _transition(db, order, "CANCELLED", user.id, reason or "Seller cancelled before payment")
            order.closed_at = clock.now()
        elif order.status == "FUNDED":
            _seller_fault_refund(db, order, "SELLER_REJECTED", user.id, reason or "Seller rejected the order")
        elif order.status == "ACCEPTED":
            _seller_fault_refund(db, order, "SELLER_CANCELLED", user.id, reason or "Seller cancelled")
        else:
            raise Conflict("This order can no longer be cancelled", code="invalid_transition")
    else:
        raise NotFound("Order not found")
    return order


def dispatch(db: Session, seller: User, order_id: uuid.UUID) -> Order:
    order = get_order(db, order_id, lock=True)
    _require_party(order, seller, "seller")
    now = clock.now()
    _transition(db, order, "DISPATCHED", seller.id)
    order.dispatched_at = now
    order.auto_release_at = now + timedelta(days=get_settings().auto_release_days)
    return order


def handover(db: Session, seller: User, order_id: uuid.UUID, pin: str) -> Order:
    """Seller enters (or scans) the buyer's PIN at handover; correct PIN releases the Stars to the seller."""
    order = get_order(db, order_id, lock=True)
    _require_party(order, seller, "seller")
    if order.status not in OPEN_FOR_HANDOVER:
        raise Conflict(f"This order is {order.status}; handover is not possible", code="invalid_transition")
    if order.handover_attempts >= get_settings().handover_pin_max_attempts or not order.handover_pin_hash:
        raise Conflict("Too many wrong PINs. Ask the buyer to issue a new PIN in the app.", code="pin_locked")
    if not hmac.compare_digest(order.handover_pin_hash, _pin_hash(order.id, pin)):
        order.handover_attempts += 1
        db.commit()  # keep the failed attempt count
        raise AppError("Wrong PIN", code="pin_invalid")
    _release(
        db,
        order,
        seller_gross=order.amount,
        buyer_refund=ZERO,
        actor_id=seller.id,
        to="RELEASED",
        reason="Buyer's handover PIN confirmed",
    )
    return order


def confirm_receipt(db: Session, buyer: User, order_id: uuid.UUID) -> Order:
    order = get_order(db, order_id, lock=True)
    _require_party(order, buyer, "buyer")
    if order.status not in OPEN_FOR_HANDOVER:
        raise Conflict(f"This order is {order.status}; it cannot be confirmed", code="invalid_transition")
    _release(
        db,
        order,
        seller_gross=order.amount,
        buyer_refund=ZERO,
        actor_id=buyer.id,
        to="RELEASED",
        reason="Buyer confirmed receipt",
    )
    return order


def reissue_pin(db: Session, buyer: User, order_id: uuid.UUID) -> str:
    order = get_order(db, order_id, lock=True)
    _require_party(order, buyer, "buyer")
    if order.status not in ("FUNDED", *OPEN_FOR_HANDOVER):
        raise Conflict(f"This order is {order.status}; no PIN is needed", code="invalid_transition")
    return _new_pin(order)


# ---------- disputes (staged negotiation and evidence come in module M4) ----------


def open_dispute(db: Session, user: User, order_id: uuid.UUID, reason: str) -> Dispute:
    order = get_order(db, order_id, lock=True)
    if user.id not in (order.buyer_id, order.seller_id):
        raise NotFound("Order not found")
    _transition(db, order, "DISPUTED", user.id, reason)
    dispute = Dispute(id=uuid.uuid4(), order_id=order.id, opened_by=user.id, reason=reason)
    db.add(dispute)
    db.flush()
    return dispute


def resolve_dispute(db: Session, mediator: User, order_id: uuid.UUID, buyer_refund: Decimal, note: str) -> Order:
    order = get_order(db, order_id, lock=True)
    if mediator.id in (order.buyer_id, order.seller_id):
        raise Forbidden("You cannot decide a dispute you are part of")
    if order.status != "DISPUTED":
        raise Conflict("This order is not in dispute", code="invalid_transition")
    if not ZERO <= buyer_refund <= order.amount:
        raise AppError(f"The refund must be between K0 and K{order.amount}", code="invalid_refund")
    dispute = db.scalars(select(Dispute).where(Dispute.order_id == order.id).with_for_update()).one()
    _release(
        db,
        order,
        seller_gross=order.amount - buyer_refund,
        buyer_refund=buyer_refund,
        actor_id=mediator.id,
        to="RESOLVED",
        reason=note or "Dispute resolved",
    )
    dispute.status = "resolved"
    dispute.buyer_refund = buyer_refund
    dispute.decision_note = note
    dispute.resolved_by = mediator.id
    dispute.resolved_at = clock.now()
    return order


# ---------- timers (run by the worker) ----------


def due_order_ids(db: Session, now: datetime, limit: int = 500) -> list[uuid.UUID]:
    stmt = (
        select(Order.id)
        .where(
            or_(
                and_(Order.status == "FUNDED", Order.accept_deadline <= now),
                and_(Order.status == "DISPATCHED", Order.auto_release_at <= now),
            )
        )
        .limit(limit)
    )
    return list(db.scalars(stmt))


def apply_timer(db: Session, order_id: uuid.UUID) -> str | None:
    """Apply an expired timer to one order. Returns the new status, or None if nothing was due."""
    order = get_order(db, order_id, lock=True)
    now = clock.now()
    if order.status == "FUNDED" and order.accept_deadline and order.accept_deadline <= now:
        minutes = get_settings().seller_accept_minutes
        _seller_fault_refund(db, order, "AUTO_REJECTED", None, f"Seller did not accept within {minutes} minutes")
        return order.status
    if order.status == "DISPATCHED" and order.auto_release_at and order.auto_release_at <= now:
        _release(
            db,
            order,
            seller_gross=order.amount,
            buyer_refund=ZERO,
            actor_id=None,
            to="RELEASED",
            reason=f"Auto-released {get_settings().auto_release_days} days after dispatch",
        )
        return order.status
    return None


# ---------- money movements ----------


def _release(
    db: Session,
    order: Order,
    *,
    seller_gross: Decimal,
    buyer_refund: Decimal,
    actor_id: uuid.UUID | None,
    to: str,
    reason: str,
) -> None:
    """Empty the order's escrow: refund part to the buyer, pay the rest to the seller less the escrow fee,
    recovering any penalties the seller owes."""
    if seller_gross + buyer_refund != order.amount:  # an explicit check: asserts are stripped under python -O
        raise AppError("Release amounts do not add up to the order amount", code="ledger_invalid")
    _assert_escrow_intact(db, order)
    _transition(db, order, to, actor_id, reason, buyer_refund=buyer_refund, seller_gross=seller_gross)
    fee = escrow_fee(seller_gross, get_settings())
    receivable = user_account(db, order.seller_id, "receivable", lock=True)
    recovered = min(receivable.balance, seller_gross - fee)
    seller_net = seller_gross - fee - recovered
    buyer_wallet = user_account(db, order.buyer_id, "wallet")
    seller_wallet = user_account(db, order.seller_id, "wallet")
    post_entry(
        db,
        "order_release" if to == "RELEASED" else "order_dispute_resolution",
        [
            debit(system_account_id(db, ESCROW), order.amount, f"Escrow closed: {order.title}"),
            credit(buyer_wallet.id, buyer_refund, f"Refund: {order.title}"),
            credit(seller_wallet.id, seller_net, f"Sale: {order.title}"),
            credit(system_account_id(db, FEE_REVENUE), fee, f"Escrow fee: {order.title}"),
            credit(receivable.id, recovered, "Owed penalty recovered from this sale"),
        ],
        order_id=order.id,
        created_by=actor_id,
        memo=reason,
    )
    order.fee_charged = fee
    order.buyer_refunded = buyer_refund
    order.seller_paid = seller_net
    order.closed_at = clock.now()


def _seller_fault_refund(db: Session, order: Order, to: str, actor_id: uuid.UUID | None, reason: str) -> None:
    """Full refund to the buyer, plus their share of the cancellation fee, which the seller pays now or owes."""
    _assert_escrow_intact(db, order)
    _transition(db, order, to, actor_id, reason)
    settings = get_settings()
    fee = cancel_fee(order.amount, settings)
    split = split_cancel_fee(fee, settings)
    seller_wallet = user_account(db, order.seller_id, "wallet", lock=True)
    paid_now = min(seller_wallet.balance, fee)
    owed = fee - paid_now
    buyer_wallet = user_account(db, order.buyer_id, "wallet")
    lines: list[Line] = [
        debit(system_account_id(db, ESCROW), order.amount, f"Escrow closed: {order.title}"),
        credit(buyer_wallet.id, order.amount, f"Full refund: {order.title}"),
        debit(seller_wallet.id, paid_now, f"Cancellation fee: {order.title}"),
        debit(
            user_account(db, order.seller_id, "receivable").id,
            owed,
            f"Cancellation fee owed, taken from your next sale: {order.title}",
        ),
        credit(buyer_wallet.id, split.counterparty, f"Compensation, seller cancelled: {order.title}"),
        credit(system_account_id(db, FEE_REVENUE), split.platform, f"Cancellation fee: {order.title}"),
    ]
    post_entry(db, "order_seller_cancel", lines, order_id=order.id, created_by=actor_id, memo=reason)
    order.fee_charged = fee
    order.buyer_refunded = order.amount + split.counterparty
    order.closed_at = clock.now()


def _buyer_cancel_with_fee(db: Session, order: Order, actor_id: uuid.UUID, reason: str) -> None:
    _assert_escrow_intact(db, order)
    _transition(db, order, "CANCELLED", actor_id, reason or "Buyer cancelled after payment")
    settings = get_settings()
    fee = cancel_fee(order.amount, settings)
    split = split_cancel_fee(fee, settings)
    post_entry(
        db,
        "order_buyer_cancel",
        [
            debit(system_account_id(db, ESCROW), order.amount, f"Escrow closed: {order.title}"),
            credit(
                user_account(db, order.buyer_id, "wallet").id,
                order.amount - fee,
                f"Refund less cancellation fee: {order.title}",
            ),
            credit(
                user_account(db, order.seller_id, "wallet").id,
                split.counterparty,
                f"Compensation, buyer cancelled: {order.title}",
            ),
            credit(system_account_id(db, FEE_REVENUE), split.platform, f"Cancellation fee: {order.title}"),
        ],
        order_id=order.id,
        created_by=actor_id,
        memo=reason,
    )
    order.fee_charged = fee
    order.buyer_refunded = order.amount - fee
    order.seller_paid = split.counterparty
    order.closed_at = clock.now()
