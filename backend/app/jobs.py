"""Background worker: applies escrow timers (20-minute accept window, 7-day auto-release), dispute deadlines
(negotiation -> mediator after 3 days; a mediator's decision becomes final after the 3-day appeal window) and
deletes expired encrypted messages (30 days).

Run with:  python -m app.jobs        (loops every MCXUS_WORKER_INTERVAL_SECONDS)
           python -m app.jobs --once
Each order is processed in its own transaction, so one failure never blocks the others.
"""

import argparse
import logging
import time

from sqlalchemy.orm import Session, sessionmaker

from app import clock
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import AppError
from app.escrow.service import apply_timer, due_order_ids

log = logging.getLogger("mcxus.worker")


def run_timers(session_factory: sessionmaker[Session] | None = None) -> dict[str, int]:
    factory = session_factory or get_sessionmaker()
    results: dict[str, int] = {}
    with factory() as db:
        ids = due_order_ids(db, clock.now())
    for order_id in ids:
        with factory() as db:
            try:
                status = apply_timer(db, order_id)
                db.commit()
            except AppError:
                db.rollback()
                log.exception("Timer failed for order %s", order_id)
                status = "FAILED"
        if status:
            results[status] = results.get(status, 0) + 1
    from app.disputes.service import apply_deadline, due_dispute_ids

    with factory() as db:
        dispute_orders = due_dispute_ids(db, clock.now())
    for order_id in dispute_orders:
        with factory() as db:
            try:
                status = apply_deadline(db, order_id)
                db.commit()
            except AppError:
                db.rollback()
                log.exception("Dispute deadline failed for order %s", order_id)
                status = "FAILED"
        if status:
            results[status] = results.get(status, 0) + 1
    return results


def purge_messages(session_factory: sessionmaker[Session] | None = None) -> int:
    """Delete encrypted messages and chat files older than MCXUS_MESSAGE_TTL_DAYS (never touches money records)."""
    from app.messaging.service import purge_expired, purge_expired_blobs

    with (session_factory or get_sessionmaker())() as db:
        from app.social.service import purge_expired_statuses

        removed = purge_expired(db) + purge_expired_blobs(db) + purge_expired_statuses(db)
        db.commit()
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    while True:
        results = run_timers()
        if results:
            log.info("Timers applied: %s", results)
        purged = purge_messages()
        if purged:
            log.info("Expired messages deleted: %s", purged)
        if args.once:
            break
        time.sleep(get_settings().worker_interval_seconds)


if __name__ == "__main__":
    main()
