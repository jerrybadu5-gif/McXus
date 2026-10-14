"""money core

Revision ID: 0001
Revises:
Create Date: 2026-10-14 02:58:54.546371
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY = ("journal_entries", "postings", "order_events")

FORBID_CHANGE_FN = """
CREATE FUNCTION mcxus_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'TRUNCATE' AND current_setting('mcxus.allow_truncate', true) = 'on' THEN
    RETURN NULL;
  END IF;
  RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;
"""

ENTRY_BALANCED_FN = """
CREATE FUNCTION mcxus_check_entry_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d numeric; c numeric; n int;
BEGIN
  SELECT coalesce(sum(amount) FILTER (WHERE side = 'D'), 0),
         coalesce(sum(amount) FILTER (WHERE side = 'C'), 0),
         count(*)
    INTO d, c, n FROM postings WHERE entry_id = NEW.entry_id;
  IF d <> c OR n < 2 THEN
    RAISE EXCEPTION 'journal entry % is unbalanced (debits %, credits %, lines %)', NEW.entry_id, d, c, n;
  END IF;
  RETURN NULL;
END $$;
"""

SYSTEM_ACCOUNTS_SQL = """
INSERT INTO ledger_accounts (id, code, name, kind, purpose, owner_id, currency, balance, allow_negative, created_at)
VALUES
  (gen_random_uuid(), 'SYS:TRUST_BANK', 'Trust account at partner bank (customer funds)', 'asset', 'trust_bank', NULL, 'PGK', 0, false, now()),
  (gen_random_uuid(), 'SYS:ESCROW', 'Stars locked in escrow', 'liability', 'escrow', NULL, 'PGK', 0, false, now()),
  (gen_random_uuid(), 'SYS:WITHDRAWALS_PENDING', 'Withdrawals approved, not yet paid by bank', 'liability', 'withdrawals_pending', NULL, 'PGK', 0, false, now()),
  (gen_random_uuid(), 'SYS:FEE_REVENUE', 'Platform fee revenue', 'revenue', 'fee_revenue', NULL, 'PGK', 0, false, now())
"""


def upgrade() -> None:
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_codes_phone_created", "otp_codes", ["phone", "created_at"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("kyc_tier", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'support', 'kyc', 'mediator', 'finance', 'compliance', 'admin')", name="role_valid"
        ),
        sa.CheckConstraint("status IN ('active', 'frozen')", name="status_valid"),
        sa.CheckConstraint("kyc_tier BETWEEN 0 AND 3", name="kyc_tier_valid"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "key"),
    )
    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("balance", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("allow_negative", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('asset', 'liability', 'revenue', 'expense', 'equity')", name="kind_valid"),
        sa.CheckConstraint("allow_negative OR balance >= 0", name="balance_not_negative"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("owner_id", "purpose", name="uq_owner_purpose"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("buyer_id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("handover_pin_hash", sa.String(length=64), nullable=True),
        sa.Column("handover_attempts", sa.SmallInteger(), nullable=False),
        sa.Column("funded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accept_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_release_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fee_charged", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("buyer_refunded", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("seller_paid", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('CREATED', 'FUNDED', 'ACCEPTED', 'DISPATCHED', 'DISPUTED', 'RELEASED', 'RESOLVED', 'CANCELLED', 'SELLER_REJECTED', 'AUTO_REJECTED', 'SELLER_CANCELLED')",
            name="status_valid",
        ),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint("buyer_id <> seller_id", name="buyer_not_seller"),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_buyer", "orders", ["buyer_id", "created_at"], unique=False)
    op.create_index("ix_orders_seller", "orders", ["seller_id", "created_at"], unique=False)
    op.create_index("ix_orders_status_deadline", "orders", ["status", "accept_deadline"], unique=False)
    op.create_index("ix_orders_status_release", "orders", ["status", "auto_release_at"], unique=False)
    op.create_table(
        "withdrawals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("fee", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("bank_account", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("bank_ref", sa.String(length=64), nullable=True),
        sa.Column("processed_by", sa.UUID(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('requested', 'paid', 'rejected')", name="status_valid"),
        sa.CheckConstraint("amount > fee AND fee >= 0", name="amount_covers_fee"),
        sa.ForeignKeyConstraint(
            ["processed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "disputes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("opened_by", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("buyer_refund", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=False),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="status_valid"),
        sa.CheckConstraint("buyer_refund IS NULL OR buyer_refund >= 0", name="refund_not_negative"),
        sa.ForeignKeyConstraint(
            ["opened_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_entries_order", "journal_entries", ["order_id"], unique=False)
    op.create_table(
        "order_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_events_order", "order_events", ["order_id", "id"], unique=False)
    op.create_table(
        "deposits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("external_ref", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status_valid"),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint("approved_by IS NULL OR approved_by <> created_by", name="maker_checker"),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["journal_entries.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_ref"),
    )
    op.create_table(
        "postings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("side", sa.String(length=1), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("side IN ('D', 'C')", name="side_valid"),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ledger_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["journal_entries.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_postings_account_created", "postings", ["account_id", "created_at"], unique=False)
    op.create_index("ix_postings_entry", "postings", ["entry_id"], unique=False)

    # Append-only financial tables: the database rejects UPDATE/DELETE, and TRUNCATE unless
    # the session sets mcxus.allow_truncate=on (used only by the test suite).
    op.execute(FORBID_CHANGE_FN)
    for table in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION mcxus_forbid_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION mcxus_forbid_change()"
        )
    # Every journal entry must balance (debits = credits, at least two lines), checked at commit.
    op.execute(ENTRY_BALANCED_FN)
    op.execute(
        "CREATE CONSTRAINT TRIGGER postings_balanced AFTER INSERT ON postings "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mcxus_check_entry_balanced()"
    )
    op.execute(SYSTEM_ACCOUNTS_SQL)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS postings_balanced ON postings")
    for table in APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mcxus_check_entry_balanced()")
    op.execute("DROP FUNCTION IF EXISTS mcxus_forbid_change()")
    op.drop_index("ix_postings_entry", table_name="postings")
    op.drop_index("ix_postings_account_created", table_name="postings")
    op.drop_table("postings")
    op.drop_table("deposits")
    op.drop_index("ix_order_events_order", table_name="order_events")
    op.drop_table("order_events")
    op.drop_index("ix_journal_entries_order", table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_table("disputes")
    op.drop_table("withdrawals")
    op.drop_index("ix_orders_status_release", table_name="orders")
    op.drop_index("ix_orders_status_deadline", table_name="orders")
    op.drop_index("ix_orders_seller", table_name="orders")
    op.drop_index("ix_orders_buyer", table_name="orders")
    op.drop_table("orders")
    op.drop_table("ledger_accounts")
    op.drop_table("idempotency_keys")
    op.drop_table("users")
    op.drop_index("ix_otp_codes_phone_created", table_name="otp_codes")
    op.drop_table("otp_codes")
