"""Database models.

Financial tables (journal_entries, postings, order_events) are append-only: the database itself
rejects UPDATE and DELETE on them (see migration 0001). Corrections are made with new entries.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Numeric(14, 2)

ROLES = ("user", "support", "kyc", "mediator", "finance", "compliance", "admin")
ACCOUNT_KINDS = ("asset", "liability", "revenue", "expense", "equity")
ORDER_STATUSES = (
    "CREATED",  # buyer placed the order, not paid yet
    "FUNDED",  # buyer paid; Stars locked in escrow; seller has N minutes to accept
    "ACCEPTED",  # seller accepted
    "DISPATCHED",  # seller sent the goods; auto-release timer running
    "DISPUTED",  # frozen until a mediator decides
    "RELEASED",  # paid out to seller (handover PIN, buyer confirmation or auto-release)
    "RESOLVED",  # dispute decided (release, refund or split)
    "CANCELLED",  # buyer cancelled (free before payment, fee after payment)
    "SELLER_REJECTED",  # seller declined; buyer refunded in full, seller penalised
    "AUTO_REJECTED",  # seller did not accept in time; same money effect as SELLER_REJECTED
    "SELLER_CANCELLED",  # seller cancelled after accepting; same money effect as SELLER_REJECTED
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="role_valid"),
        CheckConstraint("kyc_tier BETWEEN 0 AND 3", name="kyc_tier_valid"),
        CheckConstraint("status IN ('active', 'frozen')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    username: Mapped[str | None] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    role: Mapped[str] = mapped_column(String(16), default="user")
    kyc_tier: Mapped[int] = mapped_column(SmallInteger, default=0)
    status: Mapped[str] = mapped_column(String(10), default="active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OtpCode(TimestampMixin, Base):
    __tablename__ = "otp_codes"
    __table_args__ = (Index("ix_otp_codes_phone_created", "phone", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LedgerAccount(TimestampMixin, Base):
    """One account in the chart of accounts. `balance` is a cache of the postings, kept in the same transaction."""

    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint(_in("kind", ACCOUNT_KINDS), name="kind_valid"),
        CheckConstraint("allow_negative OR balance >= 0", name="balance_not_negative"),
        UniqueConstraint("owner_id", "purpose", name="uq_owner_purpose"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))
    purpose: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    currency: Mapped[str] = mapped_column(String(3), default="PGK")
    balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    allow_negative: Mapped[bool] = mapped_column(Boolean, default=False)


class JournalEntry(TimestampMixin, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (Index("ix_journal_entries_order", "order_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    memo: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Posting(TimestampMixin, Base):
    __tablename__ = "postings"
    __table_args__ = (
        CheckConstraint("side IN ('D', 'C')", name="side_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_postings_account_created", "account_id", "created_at"),
        Index("ix_postings_entry", "entry_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("journal_entries.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ledger_accounts.id"))
    side: Mapped[str] = mapped_column(String(1))
    amount: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str] = mapped_column(String(120), default="")


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(_in("status", ORDER_STATUSES), name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("buyer_id <> seller_id", name="buyer_not_seller"),
        Index("ix_orders_buyer", "buyer_id", "created_at"),
        Index("ix_orders_seller", "seller_id", "created_at"),
        Index("ix_orders_status_deadline", "status", "accept_deadline"),
        Index("ix_orders_status_release", "status", "auto_release_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(140))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="PGK")
    status: Mapped[str] = mapped_column(String(20), default="CREATED")
    handover_pin_hash: Mapped[str | None] = mapped_column(String(64))
    handover_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    funded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accept_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Money outcome, filled when the order closes (the ledger is the source of truth; these are for display)
    fee_charged: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    buyer_refunded: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    seller_paid: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrderEvent(TimestampMixin, Base):
    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_events_order", "order_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # None = system
    reason: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Dispute(TimestampMixin, Base):
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved')", name="status_valid"),
        CheckConstraint("buyer_refund IS NULL OR buyer_refund >= 0", name="refund_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    opened_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")
    buyer_refund: Mapped[Decimal | None] = mapped_column(Money)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Deposit(TimestampMixin, Base):
    """Money received into the trust bank account. Recorded by one finance user, approved by another."""

    __tablename__ = "deposits"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("approved_by IS NULL OR approved_by <> created_by", name="maker_checker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    method: Mapped[str] = mapped_column(String(20))  # bank_transfer | cash_agent | card | mobile_money
    external_ref: Mapped[str] = mapped_column(String(64), unique=True)  # bank transaction reference
    status: Mapped[str] = mapped_column(String(10), default="pending")
    entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Withdrawal(TimestampMixin, Base):
    __tablename__ = "withdrawals"
    __table_args__ = (
        CheckConstraint("status IN ('requested', 'paid', 'rejected')", name="status_valid"),
        CheckConstraint("amount > fee AND fee >= 0", name="amount_covers_fee"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    fee: Mapped[Decimal] = mapped_column(Money)
    bank_account: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10), default="requested")
    bank_ref: Mapped[str | None] = mapped_column(String(64))
    processed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyKey(TimestampMixin, Base):
    """Stops a money action running twice when a phone retries on a bad connection."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(SmallInteger)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
