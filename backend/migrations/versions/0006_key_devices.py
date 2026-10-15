"""One device per account holds a chat's keys: device-addressed Welcomes, active device.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE devices SET activated_at = COALESCE(last_seen_at, created_at)")
    op.add_column(
        "conversation_members",
        sa.Column("key_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=True),
    )
    op.add_column(
        "mls_messages",
        sa.Column("recipient_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mls_messages", "recipient_device_id")
    op.drop_column("conversation_members", "key_device_id")
    op.drop_column("devices", "activated_at")
