"""Tests run against a real PostgreSQL database (default: mcxus_test on localhost).

Set MCXUS_TEST_DATABASE_URL to use another one. The schema is rebuilt from the migrations once per run,
and every test starts from empty tables.
"""

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

TEST_DB = os.environ.get("MCXUS_TEST_DATABASE_URL", "postgresql+psycopg://mcxus:mcxus@localhost:5432/mcxus_test")
os.environ["MCXUS_DATABASE_URL"] = TEST_DB
os.environ["MCXUS_ENV"] = "test"
os.environ["MCXUS_SANDBOX_MODE"] = "true"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import clock  # noqa: E402
from app.auth.service import issue_token  # noqa: E402
from app.db import get_engine, get_sessionmaker  # noqa: E402
from app.ledger.service import ensure_user_accounts  # noqa: E402
from app.models import User  # noqa: E402
from app.wallet.service import sandbox_topup  # noqa: E402

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESET_SQL = """
SET mcxus.allow_truncate = on;
TRUNCATE postings, journal_entries, order_events, disputes, deposits, withdrawals, idempotency_keys,
         otp_codes, orders RESTART IDENTITY;
DELETE FROM ledger_accounts WHERE owner_id IS NOT NULL;
UPDATE ledger_accounts SET balance = 0;
DELETE FROM users;
"""


@pytest.fixture(scope="session", autouse=True)
def schema() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_db(schema: None) -> None:
    with get_engine().begin() as conn:
        conn.execute(text(RESET_SQL))


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(clock, "now", fake)
    return fake


@pytest.fixture
def db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


_phone_counter = iter(range(1_000_000))


def make_user(db: Session, *, tier: int = 2, role: str = "user", stars: Decimal | int = 0, name: str = "") -> User:
    user = User(id=uuid.uuid4(), phone=f"+6757{next(_phone_counter):07d}", display_name=name, role=role, kyc_tier=tier)
    db.add(user)
    db.flush()
    ensure_user_accounts(db, user.id)
    if stars:
        sandbox_topup(db, user, Decimal(stars))
    db.commit()
    return user


@pytest.fixture
def users(db: Session) -> dict[str, User]:
    return {
        "buyer": make_user(db, stars=500, name="buyer"),
        "seller": make_user(db, name="seller"),
        "mediator": make_user(db, role="mediator", name="mediator"),
        "finance_a": make_user(db, role="finance", name="finance a"),
        "finance_b": make_user(db, role="finance", name="finance b"),
    }


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(user)}"}
