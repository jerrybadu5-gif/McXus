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
    Integer,
    LargeBinary,
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

ROLES = ("user", "support", "kyc", "moderator", "mediator", "finance", "compliance", "admin")
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
    store_name: Mapped[str | None] = mapped_column(String(80))  # shown on listings; verified badge needs tier 3
    bio: Mapped[str] = mapped_column(String(500), default="")
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
        CheckConstraint("quantity >= 1", name="quantity_positive"),
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
    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id"))  # None = custom order
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1)
    stock_reserved: Mapped[bool] = mapped_column(Boolean, default=False)
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


# ---------- marketplace (module M2) ----------

LISTING_STATUSES = ("active", "paused", "sold_out", "under_review", "removed", "closed")
CONDITIONS = ("new", "like_new", "good", "fair", "not_applicable")
REPORT_REASONS = ("prohibited", "scam", "wrong_category", "offensive", "other")


class Location(Base):
    """PNG province > district > suburb. Seeded by migration 0002; staff can correct names later."""

    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("level IN ('province', 'district', 'suburb')", name="level_valid"),
        UniqueConstraint("parent_id", "name", name="uq_location_parent_name"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    level: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(80))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    region: Mapped[str] = mapped_column(String(20), default="")  # Highlands | Islands | Momase | Southern


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class Listing(TimestampMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint(_in("status", LISTING_STATUSES), name="status_valid"),
        CheckConstraint(_in("condition", CONDITIONS), name="condition_valid"),
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("quantity_available >= 0", name="quantity_not_negative"),
        Index("ix_listings_status_created", "status", "created_at"),
        Index("ix_listings_seller", "seller_id", "created_at"),
        Index("ix_listings_category", "category_id"),
        Index("ix_listings_location", "province_id", "district_id", "suburb_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    price: Mapped[Decimal] = mapped_column(Money)
    quantity_available: Mapped[int] = mapped_column(Integer, default=1)
    condition: Mapped[str] = mapped_column(String(16), default="good")
    delivery_options: Mapped[list[str]] = mapped_column(JSONB, default=list)
    province_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    suburb_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    status: Mapped[str] = mapped_column(String(16), default="active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # search_tsv: generated tsvector column + GIN index, created in migration 0002 (not mapped)


class ListingPhoto(TimestampMixin, Base):
    __tablename__ = "listing_photos"
    __table_args__ = (Index("ix_listing_photos_listing", "listing_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    key: Mapped[str] = mapped_column(String(120))  # storage key of the full image; thumbnail is key + "_t"
    width: Mapped[int] = mapped_column(SmallInteger)
    height: Mapped[int] = mapped_column(SmallInteger)
    bytes: Mapped[int] = mapped_column(Integer)


class Review(TimestampMixin, Base):
    """One rating per completed order, written by the buyer."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("stars BETWEEN 1 AND 5", name="stars_valid"),
        Index("ix_reviews_seller", "seller_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    stars: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str] = mapped_column(String(500), default="")


class ListingReport(TimestampMixin, Base):
    __tablename__ = "listing_reports"
    __table_args__ = (
        CheckConstraint(_in("reason", REPORT_REASONS), name="reason_valid"),
        CheckConstraint("status IN ('open', 'actioned', 'dismissed')", name="status_valid"),
        UniqueConstraint("listing_id", "reporter_id", name="uq_report_once"),
        Index("ix_listing_reports_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"))
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(10), default="open")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------- messaging (module M3) ----------
# The server is only a delivery service for MLS (RFC 9420) data: it stores opaque ciphertext and never
# sees message content. It does see who talks to whom and when (needed for delivery); keep that minimal.

MESSAGE_KINDS = ("welcome", "commit", "application")


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_user", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(60), default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KeyPackage(TimestampMixin, Base):
    """One-time MLS KeyPackage a device publishes so others can start an encrypted chat with it."""

    __tablename__ = "key_packages"
    __table_args__ = (Index("ix_key_packages_user_unclaimed", "user_id", "claimed_at", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (CheckConstraint("kind IN ('direct')", name="kind_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(10), default="direct")
    pair_key: Mapped[str | None] = mapped_column(String(80), unique=True)  # direct chats: one per pair of users
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id"))  # opened from a listing
    mls_ready_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # who sent the first Welcome
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationMember(TimestampMixin, Base):
    __tablename__ = "conversation_members"
    __table_args__ = (Index("ix_conversation_members_user", "user_id"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)


class MlsMessage(TimestampMixin, Base):
    """Opaque MLS message. `id` is the global delivery order and the sync cursor. Deleted after expiry."""

    __tablename__ = "mls_messages"
    __table_args__ = (
        CheckConstraint(_in("kind", MESSAGE_KINDS), name="kind_valid"),
        Index("ix_mls_messages_conversation", "conversation_id", "id"),
        Index("ix_mls_messages_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    sender_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    sender_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    kind: Mapped[str] = mapped_column(String(12))
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # Welcomes only
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
