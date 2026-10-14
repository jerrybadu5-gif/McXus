"""marketplace

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14 04:39:37.468198
"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA = Path(__file__).resolve().parent.parent / "data"
ROLES_OLD = ("user", "support", "kyc", "mediator", "finance", "compliance", "admin")
ROLES_NEW = ("user", "support", "kyc", "moderator", "mediator", "finance", "compliance", "admin")


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("parent_id", sa.SmallInteger(), nullable=True),
        sa.Column("banned", sa.Boolean(), nullable=False),
        sa.Column("sort", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("parent_id", sa.SmallInteger(), nullable=True),
        sa.Column("region", sa.String(length=20), nullable=False),
        sa.CheckConstraint("level IN ('province', 'district', 'suburb')", name="level_valid"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["locations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id", "name", name="uq_location_parent_name"),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category_id", sa.SmallInteger(), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("quantity_available", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=False),
        sa.Column("delivery_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("province_id", sa.SmallInteger(), nullable=False),
        sa.Column("district_id", sa.SmallInteger(), nullable=True),
        sa.Column("suburb_id", sa.SmallInteger(), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=8, scale=5), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=8, scale=5), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "condition IN ('new', 'like_new', 'good', 'fair', 'not_applicable')", name="condition_valid"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'sold_out', 'under_review', 'removed', 'closed')", name="status_valid"
        ),
        sa.CheckConstraint("price > 0", name="price_positive"),
        sa.CheckConstraint("quantity_available >= 0", name="quantity_not_negative"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
        ),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["locations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["province_id"],
            ["locations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["suburb_id"],
            ["locations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listings_category", "listings", ["category_id"], unique=False)
    op.create_index("ix_listings_location", "listings", ["province_id", "district_id", "suburb_id"], unique=False)
    op.create_index("ix_listings_seller", "listings", ["seller_id", "created_at"], unique=False)
    op.create_index("ix_listings_status_created", "listings", ["status", "created_at"], unique=False)
    op.create_table(
        "listing_photos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("width", sa.SmallInteger(), nullable=False),
        sa.Column("height", sa.SmallInteger(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_photos_listing", "listing_photos", ["listing_id", "position"], unique=False)
    op.create_table(
        "listing_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("reporter_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "reason IN ('prohibited', 'scam', 'wrong_category', 'offensive', 'other')", name="reason_valid"
        ),
        sa.CheckConstraint("status IN ('open', 'actioned', 'dismissed')", name="status_valid"),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", "reporter_id", name="uq_report_once"),
    )
    op.create_index("ix_listing_reports_status", "listing_reports", ["status", "created_at"], unique=False)
    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("buyer_id", sa.UUID(), nullable=False),
        sa.Column("stars", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="stars_valid"),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_reviews_seller", "reviews", ["seller_id", "created_at"], unique=False)
    op.add_column("orders", sa.Column("listing_id", sa.UUID(), nullable=True))
    op.add_column("orders", sa.Column("quantity", sa.SmallInteger(), nullable=False, server_default="1"))
    op.add_column("orders", sa.Column("stock_reserved", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_foreign_key("orders_listing_id_fkey", "orders", "listings", ["listing_id"], ["id"])
    op.create_check_constraint("quantity_positive", "orders", "quantity >= 1")
    op.add_column("users", sa.Column("store_name", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("bio", sa.String(length=500), nullable=False, server_default=""))

    # Moderator role (requirements §9)
    op.drop_constraint("role_valid", "users", type_="check")
    op.create_check_constraint("role_valid", "users", f"role IN {ROLES_NEW}")

    # Full-text search: 'simple' config (no English stemming) works for English, Tok Pisin and place names.
    op.execute(
        "ALTER TABLE listings ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS ("
        "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('simple', coalesce(description, '')), 'B')) STORED"
    )
    op.execute("CREATE INDEX ix_listings_search ON listings USING GIN (search_tsv)")

    _seed_locations()
    _seed_categories()


def _load(name: str) -> dict:
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def _seed_locations() -> None:
    table = sa.table(
        "locations", sa.column("id"), sa.column("level"), sa.column("name"), sa.column("parent_id"), sa.column("region")
    )
    rows, next_id = [], 1
    for province in _load("png_locations.json")["provinces"]:
        pid = next_id
        rows.append(
            {"id": pid, "level": "province", "name": province["name"], "parent_id": None, "region": province["region"]}
        )
        next_id += 1
        district_ids = {}
        for district in province["districts"]:
            rows.append(
                {"id": next_id, "level": "district", "name": district, "parent_id": pid, "region": province["region"]}
            )
            district_ids[district] = next_id
            next_id += 1
        for suburb in province.get("suburbs", []):  # suburbs attached to the province (NCD)
            rows.append(
                {"id": next_id, "level": "suburb", "name": suburb, "parent_id": pid, "region": province["region"]}
            )
            next_id += 1
        for district, suburbs in province.get("district_suburbs", {}).items():
            for suburb in suburbs:
                rows.append(
                    {
                        "id": next_id,
                        "level": "suburb",
                        "name": suburb,
                        "parent_id": district_ids[district],
                        "region": province["region"],
                    }
                )
                next_id += 1
    op.bulk_insert(table, rows)


def _seed_categories() -> None:
    table = sa.table(
        "categories",
        sa.column("id"),
        sa.column("slug"),
        sa.column("name"),
        sa.column("parent_id"),
        sa.column("banned"),
        sa.column("sort"),
    )
    data = _load("categories.json")
    rows, next_id = [], 1
    for sort, parent in enumerate(data["categories"]):
        pid = next_id
        rows.append(
            {
                "id": pid,
                "slug": parent["slug"],
                "name": parent["name"],
                "parent_id": None,
                "banned": False,
                "sort": sort,
            }
        )
        next_id += 1
        for child_sort, (slug, name) in enumerate(parent["children"]):
            rows.append(
                {"id": next_id, "slug": slug, "name": name, "parent_id": pid, "banned": False, "sort": child_sort}
            )
            next_id += 1
    for slug, name in data["banned"]:
        rows.append({"id": next_id, "slug": slug, "name": name, "parent_id": None, "banned": True, "sort": 99})
        next_id += 1
    op.bulk_insert(table, rows)


def downgrade() -> None:
    op.drop_constraint("role_valid", "users", type_="check")
    op.create_check_constraint("role_valid", "users", f"role IN {ROLES_OLD}")
    op.execute("DROP INDEX IF EXISTS ix_listings_search")
    op.drop_column("users", "bio")
    op.drop_column("users", "store_name")
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.drop_constraint("quantity_positive", "orders", type_="check")
    op.drop_constraint("orders_listing_id_fkey", "orders", type_="foreignkey")
    op.drop_column("orders", "stock_reserved")
    op.drop_column("orders", "quantity")
    op.drop_column("orders", "listing_id")
    op.drop_index("ix_reviews_seller", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_listing_reports_status", table_name="listing_reports")
    op.drop_table("listing_reports")
    op.drop_index("ix_listing_photos_listing", table_name="listing_photos")
    op.drop_table("listing_photos")
    op.drop_index("ix_listings_status_created", table_name="listings")
    op.drop_index("ix_listings_seller", table_name="listings")
    op.drop_index("ix_listings_location", table_name="listings")
    op.drop_index("ix_listings_category", table_name="listings")
    op.drop_table("listings")
    op.drop_table("locations")
    op.drop_table("categories")
