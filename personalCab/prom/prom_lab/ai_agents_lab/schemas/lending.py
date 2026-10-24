"""Explicit terms for a non-binding, manually reviewed DEMO offer."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DemoOffer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount_rub: Decimal = Field(gt=0, max_digits=18, decimal_places=2, allow_inf_nan=False)
    term_months: int = Field(strict=True, gt=0, le=600)
    annual_rate_fraction: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    repayment_type: Literal['ANNUITY', 'LIMIT_ONLY']
    expires_at: datetime
    fees_rub: list[Decimal]
    conditions: list[str]

    @model_validator(mode='after')
    def valid(self):
        if self.expires_at.tzinfo is None or self.expires_at <= datetime.now(timezone.utc):
            raise ValueError('Offer must have a future timezone-aware expiry')
        if any(not fee.is_finite() or fee < 0 for fee in self.fees_rub):
            raise ValueError('Explicit nonnegative fees required')
        return self


