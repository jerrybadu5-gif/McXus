"""Alembic environment. The database URL comes from MCXUS_DATABASE_URL (see app.config)."""

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

target_metadata = Base.metadata

# Created by hand in migration 0002 (generated column + GIN index); not mapped on the model.
UNMAPPED = {"search_tsv", "ix_listings_search"}


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    return name not in UNMAPPED


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = context.config.attributes.get("database_url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
