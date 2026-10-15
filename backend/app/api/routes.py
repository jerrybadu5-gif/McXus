"""HTTP API v1. Business rules live in the services; routes check roles, call a service and commit."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, freezes
from app.api.schemas import (
    DepositDecisionIn,
    DepositIn,
    DepositOut,
    HandoverIn,
    KycTierIn,
    OrderEventOut,
    OrderIn,
    OrderOut,
    OtpRequest,
    OtpVerify,
    PaidOrderOut,
    PinOut,
    ReasonIn,
    RoleIn,
    StatementLineOut,
    TokenOut,
    TopUpIn,
    UserOut,
    WalletOut,
    WithdrawalIn,
    WithdrawalOut,
    WithdrawalSettleIn,
)
from app.auth import service as auth
from app.auth.deps import current_user, require_role, signed_in_user
from app.config import get_settings
from app.db import get_db
from app.errors import NotFound
from app.escrow import service as escrow
from app.idempotency import run_once
from app.jobs import run_timers
from app.ledger import service as ledger
from app.models import Deposit, Order, OrderEvent, User, Withdrawal
from app.wallet import service as wallet

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_db)]
Me = Annotated[User, Depends(current_user)]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]
Page = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]

# ---------- auth ----------


@router.post("/auth/otp/request", status_code=202, tags=["auth"])
def otp_request(body: OtpRequest, db: DB) -> dict[str, str]:
    """Sends the code by SMS. In sandbox mode (never production) the code is also returned as `dev_code`,
    because no SMS provider is connected yet."""
    code = auth.request_code(db, body.phone)
    db.commit()
    settings = get_settings()
    if settings.sandbox_mode and settings.env != "prod":
        return {"status": "sent", "dev_code": code}
    return {"status": "sent"}


@router.post("/auth/otp/verify", tags=["auth"])
def otp_verify(body: OtpVerify, db: DB) -> TokenOut:
    user = auth.verify_code(db, body.phone, body.code)
    db.commit()
    return TokenOut(access_token=auth.issue_token(user), user_id=user.id)


AnyStatus = Annotated[User, Depends(signed_in_user)]


@router.get("/me", tags=["auth"])
def me(user: AnyStatus) -> UserOut:
    """Who is signed in; works for a frozen account too (status "frozen"), so the app can explain it."""
    return UserOut.model_validate(user)


class FreezeOut(BaseModel):
    id: uuid.UUID
    status: Literal["frozen", "appealed", "unfrozen", "upheld"]
    reason: str
    frozen_at: datetime
    appeal_text: str
    appealed_at: datetime | None
    decision_note: str
    decided_at: datetime | None
    can_appeal: bool


class AppealIn(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


@router.get("/me/freeze", tags=["auth"])
def my_freeze(user: AnyStatus, db: DB) -> FreezeOut | None:
    """Why my account is (or was last) frozen, my appeal and the decision."""
    case = freezes.view(freezes.latest_case(db, user.id))
    return FreezeOut.model_validate(case) if case else None


@router.post("/me/freeze/appeal", tags=["auth"])
def appeal_freeze(body: AppealIn, user: AnyStatus, db: DB) -> FreezeOut:
    """A frozen person explains why the account should be unfrozen (once). Staff decide in the console."""
    case = freezes.appeal(db, user, body.text)
    db.commit()
    return FreezeOut.model_validate(freezes.view(case))


# ---------- wallet ----------


@router.get("/wallet", tags=["wallet"])
def wallet_summary(user: Me, db: DB) -> WalletOut:
    return WalletOut.model_validate(wallet.summary(db, user))


@router.get("/wallet/statement", tags=["wallet"])
def wallet_statement(user: Me, db: DB, limit: Page = 50, offset: Offset = 0) -> list[StatementLineOut]:
    return [StatementLineOut.model_validate(line) for line in wallet.statement(db, user.id, limit, offset)]


@router.post("/wallet/sandbox-topup", tags=["wallet"])
def sandbox_topup(body: TopUpIn, user: Me, db: DB, key: IdemKey = None) -> WalletOut:
    """Add test Stars (sandbox only)."""
    result = run_once(
        db,
        user.id,
        key,
        {"op": "topup", **body.model_dump()},
        lambda: WalletOut.model_validate(wallet.sandbox_topup(db, user, body.amount)),
    )
    return WalletOut.model_validate(result)


@router.post("/wallet/withdrawals", tags=["wallet"])
def request_withdrawal(body: WithdrawalIn, user: Me, db: DB, key: IdemKey = None) -> WithdrawalOut:
    result = run_once(
        db,
        user.id,
        key,
        {"op": "withdraw", **body.model_dump()},
        lambda: WithdrawalOut.model_validate(wallet.request_withdrawal(db, user, body.amount, body.bank_account)),
    )
    return WithdrawalOut.model_validate(result)


@router.get("/wallet/withdrawals", tags=["wallet"])
def my_withdrawals(user: Me, db: DB, limit: Page = 50, offset: Offset = 0) -> list[WithdrawalOut]:
    rows = db.scalars(
        select(Withdrawal)
        .where(Withdrawal.user_id == user.id)
        .order_by(Withdrawal.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [WithdrawalOut.model_validate(w) for w in rows]


# ---------- orders ----------


@router.post("/orders", status_code=201, tags=["orders"])
def create_order(body: OrderIn, user: Me, db: DB, key: IdemKey = None) -> OrderOut:
    result = run_once(
        db,
        user.id,
        key,
        {"op": "order", **body.model_dump()},
        lambda: OrderOut.model_validate(escrow.create_order(db, user, body.seller_id, body.title, body.amount)),
    )
    return OrderOut.model_validate(result)


@router.get("/orders", tags=["orders"])
def my_orders(
    user: Me,
    db: DB,
    as_: Annotated[str, Query(alias="as", pattern="^(buyer|seller)$")] = "buyer",
    limit: Page = 50,
    offset: Offset = 0,
) -> list[OrderOut]:
    column = Order.buyer_id if as_ == "buyer" else Order.seller_id
    rows = db.scalars(
        select(Order).where(column == user.id).order_by(Order.created_at.desc()).limit(limit).offset(offset)
    )
    return [OrderOut.model_validate(o) for o in rows]


@router.get("/orders/{order_id}", tags=["orders"])
def get_order(order_id: uuid.UUID, user: Me, db: DB) -> OrderOut:
    return OrderOut.model_validate(escrow.get_order_for(db, user, order_id))


@router.get("/orders/{order_id}/events", tags=["orders"])
def order_events(order_id: uuid.UUID, user: Me, db: DB) -> list[OrderEventOut]:
    escrow.get_order_for(db, user, order_id)
    rows = db.scalars(select(OrderEvent).where(OrderEvent.order_id == order_id).order_by(OrderEvent.id))
    return [OrderEventOut.model_validate(e) for e in rows]


@router.post("/orders/{order_id}/pay", tags=["orders"])
def pay_order(order_id: uuid.UUID, user: Me, db: DB) -> PaidOrderOut:
    """Buyer pays; Stars are locked in escrow. The handover PIN is returned once (re-issue with /pin)."""
    order, pin = escrow.pay(db, user, order_id)
    db.commit()
    return PaidOrderOut(order=OrderOut.model_validate(order), handover_pin=pin)


@router.post("/orders/{order_id}/pin", tags=["orders"])
def reissue_pin(order_id: uuid.UUID, user: Me, db: DB) -> PinOut:
    pin = escrow.reissue_pin(db, user, order_id)
    db.commit()
    return PinOut(handover_pin=pin)


def _act(db: Session, order: Order) -> OrderOut:
    db.commit()
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/accept", tags=["orders"])
def accept_order(order_id: uuid.UUID, user: Me, db: DB) -> OrderOut:
    return _act(db, escrow.accept(db, user, order_id))


@router.post("/orders/{order_id}/reject", tags=["orders"])
def reject_order(order_id: uuid.UUID, body: ReasonIn, user: Me, db: DB) -> OrderOut:
    return _act(db, escrow.reject(db, user, order_id, body.reason))


@router.post("/orders/{order_id}/cancel", tags=["orders"])
def cancel_order(order_id: uuid.UUID, body: ReasonIn, user: Me, db: DB) -> OrderOut:
    return _act(db, escrow.cancel(db, user, order_id, body.reason))


@router.post("/orders/{order_id}/dispatch", tags=["orders"])
def dispatch_order(order_id: uuid.UUID, user: Me, db: DB) -> OrderOut:
    return _act(db, escrow.dispatch(db, user, order_id))


@router.post("/orders/{order_id}/handover", tags=["orders"])
def handover(order_id: uuid.UUID, body: HandoverIn, user: Me, db: DB) -> OrderOut:
    return _act(db, escrow.handover(db, user, order_id, body.pin))


@router.post("/orders/{order_id}/confirm-receipt", tags=["orders"])
def confirm_receipt(order_id: uuid.UUID, user: Me, db: DB) -> OrderOut:
    return _act(db, escrow.confirm_receipt(db, user, order_id))


# ---------- staff ----------

KycStaff = Annotated[User, Depends(require_role("kyc"))]
Admin = Annotated[User, Depends(require_role())]
Finance = Annotated[User, Depends(require_role("finance"))]
Oversight = Annotated[User, Depends(require_role("finance", "compliance"))]


def _user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    return user


@router.post("/admin/users/{user_id}/kyc-tier", tags=["staff"])
def set_kyc_tier(user_id: uuid.UUID, body: KycTierIn, staff: KycStaff, db: DB) -> UserOut:
    user = _user(db, user_id)
    audit.record(db, staff, "kyc_tier", "user", user.id, f"{user.kyc_tier} -> {body.kyc_tier}. {body.note}".strip())
    user.kyc_tier = body.kyc_tier
    db.commit()
    return UserOut.model_validate(user)


@router.post("/admin/users/{user_id}/role", tags=["staff"])
def set_role(user_id: uuid.UUID, body: RoleIn, staff: Admin, db: DB) -> UserOut:
    user = _user(db, user_id)
    audit.record(db, staff, "role", "user", user.id, f"{user.role} -> {body.role}")
    user.role = body.role
    db.commit()
    return UserOut.model_validate(user)


@router.post("/admin/deposits", status_code=201, tags=["staff"])
def record_deposit(body: DepositIn, staff: Finance, db: DB) -> DepositOut:
    deposit = wallet.record_deposit(db, staff, body.user_id, body.amount, body.method, body.external_ref)
    audit.record(
        db, staff, "deposit_recorded", "deposit", deposit.id, f"K{body.amount} {body.method} {body.external_ref}"
    )
    db.commit()
    return DepositOut.model_validate(deposit)


@router.post("/admin/deposits/{deposit_id}/decision", tags=["staff"])
def decide_deposit(deposit_id: uuid.UUID, body: DepositDecisionIn, staff: Finance, db: DB) -> DepositOut:
    deposit = wallet.decide_deposit(db, staff, deposit_id, body.approve)
    audit.record(db, staff, "deposit_approved" if body.approve else "deposit_rejected", "deposit", deposit.id)
    db.commit()
    return DepositOut.model_validate(deposit)


@router.get("/admin/deposits", tags=["staff"])
def list_deposits(
    staff: Finance, db: DB, status: str = "pending", limit: Page = 50, offset: Offset = 0
) -> list[DepositOut]:
    rows = db.scalars(
        select(Deposit).where(Deposit.status == status).order_by(Deposit.created_at).limit(limit).offset(offset)
    )
    return [DepositOut.model_validate(d) for d in rows]


@router.get("/admin/withdrawals", tags=["staff"])
def list_withdrawals(
    staff: Finance, db: DB, status: str = "requested", limit: Page = 50, offset: Offset = 0
) -> list[WithdrawalOut]:
    rows = db.scalars(
        select(Withdrawal)
        .where(Withdrawal.status == status)
        .order_by(Withdrawal.created_at)
        .limit(limit)
        .offset(offset)
    )
    return [WithdrawalOut.model_validate(w) for w in rows]


@router.post("/admin/withdrawals/{withdrawal_id}/settle", tags=["staff"])
def settle_withdrawal(withdrawal_id: uuid.UUID, body: WithdrawalSettleIn, staff: Finance, db: DB) -> WithdrawalOut:
    withdrawal = wallet.settle_withdrawal(db, staff, withdrawal_id, body.paid, body.bank_ref)
    audit.record(
        db,
        staff,
        "withdrawal_paid" if body.paid else "withdrawal_failed",
        "withdrawal",
        withdrawal.id,
        body.bank_ref or "",
    )
    db.commit()
    return WithdrawalOut.model_validate(withdrawal)


@router.get("/admin/reports/trial-balance", tags=["reports"])
def trial_balance(staff: Oversight, db: DB) -> dict[str, str]:
    return {kind: str(total) for kind, total in ledger.trial_balance(db).items()}


@router.get("/admin/reports/trust-reconciliation", tags=["reports"])
def trust_reconciliation(staff: Oversight, db: DB) -> dict[str, str]:
    return ledger.trust_reconciliation(db)


@router.get("/admin/reports/integrity", tags=["reports"])
def integrity(staff: Oversight, db: DB) -> dict[str, object]:
    return ledger.integrity_report(db)


@router.post("/admin/jobs/run-timers", tags=["staff"])
def run_timers_now(staff: Admin) -> dict[str, int]:
    """Apply due escrow timers now (the worker also does this every 30 seconds)."""
    return run_timers()
