"""Operator-reviewed product version metadata; units remain explicit."""
from datetime import date,datetime,timezone
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .models import LoanRequest


class ProductApproval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    policy_version: str=Field(min_length=1,max_length=100)
    effective_from: date
    effective_to: date
    source_checked_at: datetime
    rule_mappings: dict[str,dict]=Field(default_factory=dict)

    @model_validator(mode='after')
    def valid(self):
        if self.effective_to<self.effective_from or self.source_checked_at.tzinfo is None or self.source_checked_at>datetime.now(timezone.utc):
            raise ValueError('Explicit valid dates and source timestamp required')
        for mapping in self.rule_mappings.values():
            if set(mapping)-{'field','verified_only'} or mapping.get('field') not in LoanRequest.model_fields or type(mapping.get('verified_only',True)) is not bool:
                raise ValueError('Only explicit known field mappings are supported; units are not converted')
        return self


