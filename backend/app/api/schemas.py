"""Request and response bodies. Money is sent and returned as a string with 2 decimals (e.g. "150.00")."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Amount = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2, description="PGK / Stars, e.g. 150.00")]


class OtpRequest(BaseModel):
    phone: str = Field(examples=["71234567"])


class OtpVerify(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    phone: str | None
    display_name: str
    role: str
    kyc_tier: int
    status: str


class WalletOut(BaseModel):
    balance: Decimal
    penalties_owed: Decimal
    kyc_tier: int
    kyc_tier_name: str
    max_balance: Decimal | None
    monthly_in_limit: Decimal | None
    monthly_in_used: Decimal
    sandbox: bool


class StatementLineOut(BaseModel):
    at: datetime
    kind: str
    order_id: uuid.UUID | None
    description: str
    amount: Decimal = Field(description="Positive = Stars in, negative = Stars out")


class TopUpIn(BaseModel):
    amount: Amount


class WithdrawalIn(BaseModel):
    amount: Amount
    bank_account: str = Field(min_length=4, max_length=120, examples=["BSP 1001234567 J Badu"])


class WithdrawalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    fee: Decimal
    bank_account: str
    status: str
    bank_ref: str | None
    created_at: datetime


class OrderIn(BaseModel):
    seller_id: uuid.UUID
    title: str = Field(min_length=2, max_length=140)
    amount: Amount


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    buyer_id: uuid.UUID
    seller_id: uuid.UUID
    title: str
    amount: Decimal
    currency: str
    status: str
    funded_at: datetime | None
    accept_deadline: datetime | None
    accepted_at: datetime | None
    dispatched_at: datetime | None
    auto_release_at: datetime | None
    closed_at: datetime | None
    fee_charged: Decimal
    buyer_refunded: Decimal
    seller_paid: Decimal
    created_at: datetime


class PaidOrderOut(BaseModel):
    order: OrderOut
    handover_pin: str = Field(description="Show only to the buyer. The seller enters it at handover.")


class PinOut(BaseModel):
    handover_pin: str


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class DisputeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class HandoverIn(BaseModel):
    pin: str = Field(pattern=r"^\d{6}$")


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    actor_id: uuid.UUID | None
    reason: str
    created_at: datetime


# ---------- staff ----------


class KycTierIn(BaseModel):
    kyc_tier: int = Field(ge=0, le=3)


class RoleIn(BaseModel):
    role: Literal["user", "support", "kyc", "mediator", "finance", "compliance", "admin"]


class DepositIn(BaseModel):
    user_id: uuid.UUID
    amount: Amount
    method: Literal["bank_transfer", "cash_agent", "card", "mobile_money"]
    external_ref: str = Field(min_length=3, max_length=64, description="Bank transaction reference")


class DepositDecisionIn(BaseModel):
    approve: bool


class DepositOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    method: str
    external_ref: str
    status: str
    created_by: uuid.UUID
    approved_by: uuid.UUID | None
    created_at: datetime


class WithdrawalSettleIn(BaseModel):
    paid: bool
    bank_ref: str | None = Field(default=None, max_length=64)


class ResolveIn(BaseModel):
    buyer_refund: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    note: str = Field(min_length=5, max_length=2000)
