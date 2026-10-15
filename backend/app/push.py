"""Content-free push notifications through Firebase Cloud Messaging (HTTP v1).

A push says only "sync now" (`{"t": "sync"}`). The phone then fetches and decrypts the new messages itself, so
Google never sees who wrote what. Without MCXUS_FCM_CREDENTIALS_FILE pushes are simply off (phones still get
messages while McXus is open).

Uses only the standard library plus PyJWT (already a dependency) to sign the service-account token (RS256).
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any

import jwt

from app.config import get_settings

log = logging.getLogger("mcxus.push")
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class Fcm:
    def __init__(self, credentials: dict[str, Any], opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        if not str(credentials.get("token_uri", "")).startswith("https://"):
            raise ValueError("Firebase credentials: token_uri must be an https:// URL")
        self.creds = credentials
        self.project = credentials["project_id"]
        self._open = opener
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    def _access_token(self) -> str:
        with self._lock:
            if self._token and self._token[1] > time.time() + 60:
                return self._token[0]
            now = int(time.time())
            assertion = jwt.encode(
                {
                    "iss": self.creds["client_email"],
                    "scope": SCOPE,
                    "aud": self.creds["token_uri"],
                    "iat": now,
                    "exp": now + 3600,
                },
                self.creds["private_key"],
                algorithm="RS256",
            )
            body = f"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion={assertion}".encode()
            token_uri = self.creds["token_uri"]  # checked to be https:// in __init__
            request = urllib.request.Request(token_uri, data=body, method="POST")  # noqa: S310
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            with self._open(request, timeout=10) as response:
                data = json.loads(response.read())
            self._token = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
            return self._token[0]

    def send(self, token: str) -> bool:
        """Wake one phone. Returns False if the token is no longer valid (app uninstalled)."""
        message = {
            "message": {
                "token": token,
                "data": {"t": "sync"},
                "android": {"priority": "high", "collapse_key": "mcxus-sync", "ttl": "86400s"},
            }
        }
        request = urllib.request.Request(
            f"https://fcm.googleapis.com/v1/projects/{self.project}/messages:send",
            data=json.dumps(message).encode(),
            method="POST",
        )
        request.add_header("Authorization", f"Bearer {self._access_token()}")
        request.add_header("Content-Type", "application/json")
        try:
            with self._open(request, timeout=10):
                return True
        except urllib.error.HTTPError as err:
            if err.code in (400, 404):  # UNREGISTERED / INVALID_ARGUMENT: drop the token
                return False
            log.warning("FCM push failed: %s", err.code)
            return True


_client: Fcm | None = None
_loaded = False


def client() -> Fcm | None:
    global _client, _loaded
    if not _loaded:
        _loaded = True
        path = get_settings().fcm_credentials_file
        if path:
            with open(path, encoding="utf-8") as f:
                _client = Fcm(json.load(f))
            log.info("Push notifications on (Firebase project %s)", _client.project)
    return _client


def notify(tokens: Iterable[str]) -> list[str]:
    """Send the content-free wake-up to each token. Returns tokens that are dead and should be removed."""
    fcm = client()
    if fcm is None:
        return []
    dead = []
    for token in dict.fromkeys(tokens):
        try:
            if not fcm.send(token):
                dead.append(token)
        except Exception:  # noqa: BLE001 - a push problem must never break messaging
            log.exception("Push failed")
    return dead
