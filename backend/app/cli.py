"""Admin command line.

python -m app.cli make-admin 71234567       give a phone number the admin role (creates the user)
python -m app.cli seed-demo                 sandbox only: demo buyer, seller, staff (prints their phones)
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
]


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
