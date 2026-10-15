"""Admin command line.

python -m app.cli make-admin 71234567       give a phone number the admin role (creates the user)
python -m app.cli seed-demo                 sandbox only: demo buyer, seller, staff (prints their phones)
python -m app.cli seed-disputes             sandbox only: three sample disputes between the demo buyer and seller
"""

import argparse
import uuid

from sqlalchemy import select

from app.auth.service import issue_token, normalise_phone
from app.config import get_settings
from app.db import get_sessionmaker
from app.ledger.service import ensure_user_accounts
from app.models import User

DEMO_USERS = [
    # phone, name, role, tier
    ("+67570000001", "Demo Buyer", "user", 2),
    ("+67570000002", "Demo Seller", "user", 2),
    ("+67570000003", "Finance Officer A", "finance", 2),
    ("+67570000004", "Finance Officer B", "finance", 2),
    ("+67570000005", "Dispute Mediator", "mediator", 2),
    ("+67570000006", "Admin", "admin", 2),
    ("+67570000007", "Moderator", "moderator", 2),
    ("+67570000008", "Second Buyer", "user", 2),
    ("+67570000009", "Compliance Officer", "compliance", 2),
    ("+67570000010", "KYC Reviewer", "kyc", 2),
    ("+67570000011", "Support Desk", "support", 2),
]


def seed_disputes() -> None:
    """Three sample disputes so the console and the app have something to show (sandbox only)."""
    from decimal import Decimal

    from app.disputes import service as disputes
    from app.escrow import service as escrow
    from app.wallet.service import sandbox_topup

    with get_sessionmaker()() as db:

        def get(phone: str) -> User:
            user = db.scalars(select(User).where(User.phone == phone)).first()
            if user is None:
                raise SystemExit("Run seed-demo first")
            return user

        buyer, seller, mediator = get("+67570000001"), get("+67570000002"), get("+67570000005")
        sandbox_topup(db, buyer, Decimal("655.00"))  # exactly the three orders below
        made = []
        for title, amount, reason in [
            ("Solar lamp with phone charger", "120.00", "The lamp arrived with a cracked panel and does not charge."),
            ("Bilum, large, handmade", "85.00", "The seller sent a smaller bilum than in the photos."),
            (
                "Second-hand Samsung A15",
                "450.00",
                "The phone switches off after ten minutes; the seller said it was fine.",
            ),
        ]:
            order = escrow.create_order(db, buyer, seller.id, title, Decimal(amount))
            escrow.pay(db, buyer, order.id)
            escrow.accept(db, seller, order.id)
            escrow.dispatch(db, seller, order.id)
            disputes.open_dispute(db, buyer, order.id, reason)
            made.append(order)
        lamp, bilum, phone = made
        disputes.make_offer(db, seller, lamp.id, Decimal("40.00"), "I can refund K40 for the panel")
        disputes.add_statement(db, seller, bilum.id, "It is the bilum in the photos; the photos were taken close up.")
        disputes.escalate(db, buyer, bilum.id)
        disputes.escalate(db, seller, phone.id)
        disputes.decide(db, mediator, phone.id, Decimal("300.00"), "The battery fault was there before the sale.")
        disputes.appeal(db, seller, phone.id, "The buyer dropped the phone; the screen has a new crack.")
        db.commit()
        print("Disputes made: negotiating (lamp), with a mediator (bilum), appeal (phone).")


def upsert_user(phone: str, name: str, role: str, tier: int) -> User:
    with get_sessionmaker()() as db:
        user = db.scalars(select(User).where(User.phone == phone)).first()
        if user is None:
            user = User(id=uuid.uuid4(), phone=phone)
            db.add(user)
            db.flush()
        user.display_name, user.role, user.kyc_tier = name, role, tier
        ensure_user_accounts(db, user.id)
        db.commit()
        return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("make-admin")
    admin.add_argument("phone")
    sub.add_parser("seed-demo")
    sub.add_parser("seed-disputes")
    token = sub.add_parser("dev-token")
    token.add_argument("phone")
    args = parser.parse_args()

    if args.command == "make-admin":
        user = upsert_user(normalise_phone(args.phone), "Administrator", "admin", 2)
        print(f"{user.phone} is now an admin ({user.id})")
    elif args.command == "seed-demo":
        if not get_settings().sandbox_mode:
            raise SystemExit("seed-demo only runs in sandbox mode")
        for phone, name, role, tier in DEMO_USERS:
            user = upsert_user(phone, name, role, tier)
            print(f"{name:<20} {phone}  role={role:<9} tier={tier}  id={user.id}")
        print("Sign in with POST /v1/auth/otp/request; the code is printed in the API window.")
    elif args.command == "seed-disputes":
        if not get_settings().sandbox_mode:
            raise SystemExit("seed-disputes only runs in sandbox mode")
        seed_disputes()
    elif args.command == "dev-token":
        if not get_settings().sandbox_mode:
            raise SystemExit("dev-token only runs in sandbox mode")
        with get_sessionmaker()() as db:
            found = db.scalars(select(User).where(User.phone == normalise_phone(args.phone))).first()
            if found is None:
                raise SystemExit("No user with that phone; run seed-demo first")
            print(issue_token(found))


if __name__ == "__main__":
    main()
