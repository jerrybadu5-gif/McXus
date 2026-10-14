"""End-to-end smoke test against a running McXus API (sandbox). Uses only the Python standard library.

    docker compose up -d
    python scripts/smoke_test.py            (from the mcxus folder)

It seeds demo users, then walks one order from payment to release over HTTP and checks the books balance.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

API = "http://localhost:8000"


def cli(*args: str) -> str:
    cmd = ["docker", "compose", "exec", "-T", "api", "python", "-m", "app.cli", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def call(method: str, path: str, token: str | None = None, body: dict | None = None, idem: bool = False) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idem:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed local URL)
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        sys.exit(f"FAILED {method} {path}: {err.code} {err.read().decode()}")


def check(label: str, condition: bool) -> None:
    print(("PASS  " if condition else "FAIL  ") + label)
    if not condition:
        sys.exit(1)


def main() -> None:
    check("API is up in sandbox mode", call("GET", "/health") == {"status": "ok", "sandbox": True})
    print(cli("seed-demo"))
    buyer, seller, finance = (cli("dev-token", p) for p in ("70000001", "70000002", "70000003"))
    seller_id = call("GET", "/v1/me", seller)["id"]

    start = call("GET", "/v1/wallet", buyer)["balance"]
    call("POST", "/v1/wallet/sandbox-topup", buyer, {"amount": "300.00"}, idem=True)
    after_topup = call("GET", "/v1/wallet", buyer)["balance"]
    check(f"buyer topped up K300 ({start} -> {after_topup})", float(after_topup) - float(start) == 300)

    order = call("POST", "/v1/orders", buyer, {"seller_id": seller_id, "title": "Smoke test bilum", "amount": "100.00"},
                 idem=True)
    paid = call("POST", f"/v1/orders/{order['id']}/pay", buyer)
    check("order paid into escrow", paid["order"]["status"] == "FUNDED")
    check("seller accepted", call("POST", f"/v1/orders/{order['id']}/accept", seller)["status"] == "ACCEPTED")
    check("seller dispatched", call("POST", f"/v1/orders/{order['id']}/dispatch", seller)["status"] == "DISPATCHED")
    done = call("POST", f"/v1/orders/{order['id']}/handover", seller, {"pin": paid["handover_pin"]})
    check(f"handover PIN released K{done['seller_paid']} to seller (fee K{done['fee_charged']})",
          done["status"] == "RELEASED" and done["seller_paid"] == "97.00")
    integrity = call("GET", "/v1/admin/reports/integrity", finance)
    check("ledger integrity: every entry balanced, cached balances match postings", integrity["ok"] is True)
    recon = call("GET", "/v1/admin/reports/trust-reconciliation", finance)
    check(f"trust account covers customer funds (position K{recon['safeguarding_position']})",
          float(recon["safeguarding_position"]) >= 0)
    print("\nSmoke test passed. API docs: http://localhost:8000/docs")


if __name__ == "__main__":
    main()
