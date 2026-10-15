"""Three-stage disputes: negotiation offers, evidence, mediator deadline, appeal (ADR 0011); staff audit log.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
STAGES = "status IN ('negotiation', 'mediation', 'decided', 'appeal', 'resolved')"


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def upgrade() -> None:
    op.drop_constraint("status_valid", "disputes", type_="check")
    op.alter_column("disputes", "status", type_=sa.String(12), server_default="negotiation")
    for col in ("negotiate_until", "escalated_at", "mediator_due", "decided_at", "appeal_until", "appealed_at"):
        op.add_column("disputes", _ts(col))
    op.add_column("disputes", sa.Column("mediator_id", UUID, sa.ForeignKey("users.id"), nullable=True))
    op.add_column("disputes", sa.Column("proposed_refund", sa.Numeric(14, 2), nullable=True))
    op.add_column("disputes", sa.Column("proposed_note", sa.Text(), nullable=False, server_default=""))
    op.add_column("disputes", sa.Column("decided_by", UUID, sa.ForeignKey("users.id"), nullable=True))
    op.add_column("disputes", sa.Column("buyer_accepted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("disputes", sa.Column("seller_accepted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("disputes", sa.Column("appealed_by", UUID, sa.ForeignKey("users.id"), nullable=True))
    op.add_column("disputes", sa.Column("appeal_reason", sa.Text(), nullable=False, server_default=""))
    op.add_column("disputes", sa.Column("outcome", sa.String(10), nullable=True))
    # Disputes opened before M4 go straight to a mediator, due in a week.
    op.execute(
        "UPDATE disputes SET status = 'mediation', escalated_at = created_at, mediator_due = now() + interval '7 days' "
        "WHERE status = 'open'"
    )
    op.execute("UPDATE disputes SET outcome = 'mediator' WHERE status = 'resolved'")
    op.create_check_constraint("stage_valid", "disputes", STAGES)
    op.create_check_constraint("proposed_not_negative", "disputes", "proposed_refund IS NULL OR proposed_refund >= 0")
    op.create_check_constraint(
        "outcome_valid", "disputes", "outcome IS NULL OR outcome IN ('agreed', 'mediator', 'senior')"
    )
    op.create_index("ix_disputes_status", "disputes", ["status"])

    op.create_table(
        "dispute_offers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dispute_id", UUID, sa.ForeignKey("disputes.id"), nullable=False, index=True),
        sa.Column("by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("buyer_refund", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        _ts("answered_at"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("buyer_refund >= 0", name="refund_not_negative"),
        sa.CheckConstraint(
            "status IN ('open', 'accepted', 'rejected', 'withdrawn', 'replaced', 'lapsed')", name="status_valid"
        ),
    )
    op.create_table(
        "dispute_evidence",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dispute_id", UUID, sa.ForeignKey("disputes.id"), nullable=False, index=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_key", sa.String(200), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('statement', 'photo')", name="kind_valid"),
    )
    op.create_table(
        "dispute_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("dispute_id", UUID, sa.ForeignKey("disputes.id"), nullable=False, index=True),
        sa.Column("actor_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "staff_actions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", UUID, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False, index=True),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staff_actions")
    op.drop_table("dispute_events")
    op.drop_table("dispute_evidence")
    op.drop_table("dispute_offers")
    op.drop_index("ix_disputes_status", "disputes")
    for name in ("outcome_valid", "proposed_not_negative", "stage_valid"):
        op.drop_constraint(name, "disputes", type_="check")
    op.execute("UPDATE disputes SET status = 'open' WHERE status <> 'resolved'")
    for col in (
        "outcome",
        "appeal_reason",
        "appealed_by",
        "seller_accepted",
        "buyer_accepted",
        "decided_by",
        "proposed_note",
        "proposed_refund",
        "mediator_id",
        "appealed_at",
        "appeal_until",
        "decided_at",
        "mediator_due",
        "escalated_at",
        "negotiate_until",
    ):
        op.drop_column("disputes", col)
    op.alter_column("disputes", "status", type_=sa.String(10), server_default="open")
    op.create_check_constraint("status_valid", "disputes", "status IN ('open', 'resolved')")
