"""Delivery / meet-up location: GPS point first, address as the second identifier.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("meetup_address", sa.String(200), nullable=False, server_default=""))
    op.add_column("orders", sa.Column("delivery_method", sa.String(20), nullable=True))
    op.add_column("orders", sa.Column("delivery_latitude", sa.Numeric(8, 5), nullable=True))
    op.add_column("orders", sa.Column("delivery_longitude", sa.Numeric(8, 5), nullable=True))
    op.add_column("orders", sa.Column("delivery_address", sa.String(200), nullable=False, server_default=""))


def downgrade() -> None:
    for column in ("delivery_address", "delivery_longitude", "delivery_latitude", "delivery_method"):
        op.drop_column("orders", column)
    op.drop_column("listings", "meetup_address")
