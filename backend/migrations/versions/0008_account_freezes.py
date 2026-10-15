"""Account freezes with reasons, appeals and unfreeze decisions (M4.1).

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "account_freezes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="frozen"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("frozen_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("appeal_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("appealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('frozen', 'appealed', 'unfrozen', 'upheld')", name="status_valid"),
    )
    op.create_index("ix_account_freezes_user", "account_freezes", ["user_id", "status"])
    # Accounts frozen before this module: open a case, taking the reason and staff member from the staff log.
    op.execute(
        """
        INSERT INTO account_freezes (id, user_id, status, reason, frozen_by, frozen_at)
        SELECT gen_random_uuid(), u.id, 'frozen',
               COALESCE(NULLIF(a.detail, ''), 'Frozen before appeals existed (no reason recorded)'),
               a.actor_id, COALESCE(a.created_at, now())
        FROM users u
        LEFT JOIN LATERAL (
            SELECT detail, actor_id, created_at FROM staff_actions
            WHERE action = 'user_frozen' AND target_id = u.id::text ORDER BY id DESC LIMIT 1
        ) a ON true
        WHERE u.status = 'frozen'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_account_freezes_user", "account_freezes")
    op.drop_table("account_freezes")
