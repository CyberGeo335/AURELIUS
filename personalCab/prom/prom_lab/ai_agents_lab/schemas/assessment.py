"""Explicit reviewed feature and cash-flow inputs; no inferred units."""
import math
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .features import BASELINE_FEATURES, DYNAMIC_FEATURES


class RegisteredModel(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model_id:str=Field(min_length=1,max_length=50)
    kind:Literal['baseline','dynamic']
    path:str=Field(min_length=1)
    sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    schema_version:Literal['CATBOOST-V2-16','CATBOOST-V2-23']
    target:Literal['synthetic_default_event']
    population:Literal['synthetic_sme']
    currency:Literal['RUB']
    approved_for_real_lending:Literal[False]
    calibrator:None
    supported_products:list[Literal['R01','R02','R03']]
    supported_term_months:list[int]=Field(min_length=1)
    prediction_time:Literal['origination','start_of_month']

    @model_validator(mode='after')
    def semantic_contract(self):
        expected=('CATBOOST-V2-16','origination') if self.kind=='baseline' else ('CATBOOST-V2-23','start_of_month')
        if (self.schema_version,self.prediction_time)!=expected:
            raise ValueError('Registered target timing and schema do not match the model kind')
        return self


class ModelRegistry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:str=Field(min_length=1)
    models:list[RegisteredModel]

    @model_validator(mode='after')
    def unique_models(self):
        if len({model.kind for model in self.models})!=len(self.models):
            raise ValueError('Ambiguous model kind in registry')
        return self


class CashflowScenario(BaseModel):
    model_config=ConfigDict(extra='forbid')
    cfads_monthly_rub:Decimal=Field(ge=0,allow_inf_nan=False)
    existing_debt_service_monthly_rub:Decimal=Field(ge=0,allow_inf_nan=False)
    source_ref:str=Field(min_length=1,max_length=500)
    basis_version:str=Field(min_length=1,max_length=100)
    stress_cfads_monthly_rub:list[Decimal]=Field(default_factory=list,max_length=20)
    fees_rub:list[Decimal] | None=None

    @model_validator(mode='after')
    def valid(self):
        if any(not value.is_finite() or value<0 for value in [*self.stress_cfads_monthly_rub,*(self.fees_rub or [])]):
            raise ValueError('Explicit nonnegative finite scenario inputs required')
        return self


class FeatureInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['CATBOOST-V2-16', 'CATBOOST-V2-23']
    kind: Literal['baseline', 'dynamic'] = 'baseline'
    source_ref: str = Field(min_length=1, max_length=500)
    features: dict[str, Any]
    currency: Literal['RUB'] = 'RUB'
    annual_rate_unit: Literal['fraction'] = 'fraction'
    population: Literal['synthetic_sme'] = 'synthetic_sme'
    cashflow_scenario:CashflowScenario | None=None

    @model_validator(mode='after')
    def validate_features(self):
        names = BASELINE_FEATURES if self.kind == 'baseline' else DYNAMIC_FEATURES
        if self.schema_version != f'CATBOOST-V2-{len(names)}':
            raise ValueError('Feature schema and model kind differ')
        if set(self.features) != set(names):
            raise ValueError('Features must exactly match the registered schema')
        for name, value in self.features.items():
            if name in {'industry', 'entity_type'}:
                allowed = {'retail', 'services', 'manufacturing', 'construction', 'transport', 'agriculture'} if name == 'industry' else {'IP', 'OOO'}
                if value not in allowed:
                    raise ValueError(f'Unsupported category: {name}')
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'Finite numeric feature required: {name}')
        for name in ('age_months', 'requested_amount', 'term_months', 'annual_rate', 'month_on_book'):
            if self.features[name] <= 0:
                raise ValueError(f'Positive feature required: {name}')
        if not 0 <= self.features['annual_rate'] <= 1:
            raise ValueError('annual_rate must be an explicitly supplied fraction')
        for name in ('term_months', 'month_on_book', 'age_months'):
            if int(self.features[name]) != self.features[name]:
                raise ValueError(f'Integer feature required: {name}')
        if self.features['term_months'] > 600 or self.features['month_on_book'] > self.features['term_months']:
            raise ValueError('Invalid model observation horizon')
        if self.kind == 'baseline' and self.features['month_on_book'] != 1:
            raise ValueError('Origination baseline starts at month 1')
        return self


