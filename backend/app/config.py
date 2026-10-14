"""Settings, read from MCXUS_* environment variables or backend/.env.

Every fee, limit and timer lives here so it can be tuned without code changes.
"""

from decimal import Decimal
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-change-me-not-for-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCXUS_", env_file=".env", extra="ignore")

    env: str = "dev"  # dev | test | prod
    database_url: str = "postgresql+psycopg://mcxus:mcxus@localhost:5432/mcxus"
    jwt_secret: str = DEV_SECRET
    jwt_minutes: int = 60
    otp_secret: str = DEV_SECRET
    cors_origins: list[str] = ["http://localhost:5173"]

    # Sandbox: test Stars only, self-service top-up allowed. Must stay on until a licensed issuer partner is live.
    sandbox_mode: bool = True
    sandbox_topup_max: Decimal = Decimal("1000.00")

    # Escrow timers
    seller_accept_minutes: int = 20  # reject or let this pass: no penalty
    seller_penalty_free_minutes: int = 25  # seller may cancel an accepted order free until this long after payment
    auto_release_days: int = 7
    handover_pin_max_attempts: int = 5

    # Fees (1 Star = 1 PGK)
    escrow_fee_rate: Decimal = Decimal("0.03")  # paid by seller on release
    escrow_fee_min: Decimal = Decimal("1.00")
    escrow_fee_max: Decimal = Decimal("150.00")
    cancel_fee_rate: Decimal = Decimal("0.05")  # paid by whoever cancels after payment
    cancel_fee_min: Decimal = Decimal("2.00")
    cancel_fee_counterparty_share: Decimal = Decimal("0.50")  # rest goes to the platform
    withdrawal_fee: Decimal = Decimal("2.00")

    # Auth
    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5
    otp_max_per_10_min: int = 3

    worker_interval_seconds: int = 30

    @model_validator(mode="after")
    def _prod_guards(self) -> "Settings":
        if self.env == "prod":
            if DEV_SECRET in (self.jwt_secret, self.otp_secret) or len(self.jwt_secret) < 32:
                raise ValueError("Set MCXUS_JWT_SECRET and MCXUS_OTP_SECRET to long random values in production")
            if self.sandbox_mode:
                raise ValueError("Sandbox mode cannot run with MCXUS_ENV=prod until a licensed issuer is connected")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
