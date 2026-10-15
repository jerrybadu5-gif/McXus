"""Groups, encrypted chat media and push tokens (M3.2).

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("kind_valid", "conversations", type_="check")
    op.create_check_constraint("kind_valid", "conversations", "kind IN ('direct', 'group')")
    op.add_column("conversations", sa.Column("title", sa.String(80), nullable=True))
    op.add_column("conversations", sa.Column("epoch", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversation_members", sa.Column("role", sa.String(8), nullable=False, server_default="member"))

    op.drop_constraint("kind_valid", "mls_messages", type_="check")
    op.create_check_constraint("kind_valid", "mls_messages", "kind IN ('welcome', 'commit', 'application', 'event')")
    op.add_column("mls_messages", sa.Column("epoch", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("push_token", sa.String(512), nullable=True))

    op.create_table(
        "media_blobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("uploader_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_media_blobs_expires", "media_blobs", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_media_blobs_expires", table_name="media_blobs")
    op.drop_table("media_blobs")
    op.drop_column("devices", "push_token")
    op.drop_column("mls_messages", "epoch")
    op.drop_constraint("kind_valid", "mls_messages", type_="check")
    op.create_check_constraint("kind_valid", "mls_messages", "kind IN ('welcome', 'commit', 'application')")
    op.drop_column("conversation_members", "role")
    op.drop_column("conversations", "epoch")
    op.drop_column("conversations", "title")
    op.drop_constraint("kind_valid", "conversations", type_="check")
    op.create_check_constraint("kind_valid", "conversations", "kind IN ('direct')")
