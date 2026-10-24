"""M4: verified, versioned feature inputs and real synthetic CatBoost inference.

No seeded PD, inferred units or invented business ratios enter this service.
"""
import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


from ..schemas.features import BASELINE_FEATURES, DYNAMIC_FEATURES
from ..schemas.assessment import FeatureInput, CashflowScenario, ModelRegistry

ROOT = Path(__file__).resolve().parents[5]


class AssessmentService:
    def __init__(self, registry=None, model_loader=None):
        try:
            source=registry if registry is not None else json.loads((ROOT / 'scoring/models/registry.json').read_text())
            self.registry=ModelRegistry.model_validate(source).model_dump(mode='json')
            self.registry_error=False
        except (OSError,ValueError,TypeError):
            self.registry={'version':'UNAVAILABLE','models':[]}
            self.registry_error=True
        self.model_loader = model_loader

    def assess(self, feature_input, *, product_code, request, horizon=12):
        if self.registry_error:
            return {'status':'TECHNICAL_ERROR','probability':None,'reasons':['MODEL_REGISTRY_UNAVAILABLE'],'is_binding':False}
        if not any(product_code in item['supported_products'] for item in self.registry['models']):
            return {'status':'UNSUPPORTED_MODEL','probability':None,'reasons':['PRODUCT_OR_MODEL_UNSUPPORTED'],'is_binding':False}
        if feature_input is None:
            return {'status':'INSUFFICIENT_DATA', 'probability':None, 'reasons':['VERIFIED_FEATURE_INPUT_REQUIRED'], 'is_binding':False}
        bundle = FeatureInput.model_validate(feature_input)
        entry = next((item for item in self.registry['models'] if item['kind'] == bundle.kind), None)
        if entry is None or product_code not in entry['supported_products']:
            return {'status':'UNSUPPORTED_MODEL', 'probability':None, 'reasons':['PRODUCT_OR_MODEL_UNSUPPORTED'], 'is_binding':False}
        if bundle.features['term_months'] not in entry['supported_term_months']:
            return {'status':'UNSUPPORTED_MODEL','probability':None,'reasons':['TERM_OUTSIDE_SYNTHETIC_TRAINING_DOMAIN'],'is_binding':False}
        if (bundle.features['requested_amount'], bundle.features['term_months']) != (request['amount_rub'], request['term_months']):
            return {'status':'INSUFFICIENT_DATA', 'probability':None, 'reasons':['FEATURE_REQUEST_MISMATCH'], 'is_binding':False}
        if request.get('legal_form') and bundle.features['entity_type'] != request['legal_form']:
            return {'status':'INSUFFICIENT_DATA', 'probability':None, 'reasons':['FEATURE_SUBJECT_MISMATCH'], 'is_binding':False}
        path = (ROOT / entry['path']).resolve()
        if not path.is_relative_to(ROOT / 'scoring/models') or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            return {'status':'TECHNICAL_ERROR', 'probability':None, 'reasons':['MODEL_ARTIFACT_MISMATCH'], 'is_binding':False}
        if self.model_loader:
            model = self.model_loader(path)
        else:
            from catboost import CatBoostClassifier
            model = CatBoostClassifier()
            model.load_model(str(path))
        names = BASELINE_FEATURES if bundle.kind == 'baseline' else DYNAMIC_FEATURES
        if model.feature_names_ != names:
            return {'status':'TECHNICAL_ERROR', 'probability':None, 'reasons':['MODEL_SCHEMA_MISMATCH'], 'is_binding':False}
        if type(horizon) is not int or not 1 <= horizon <= 60:
            raise ValueError('Horizon must be 1..60 months')
        months = 1 if bundle.kind == 'dynamic' else min(horizon, int(bundle.features['term_months']))
        rows = []
        for month in range(1, months + 1):
            values = dict(bundle.features)
            if bundle.kind == 'baseline':
                values['month_on_book'] = month
            rows.append([values[name] for name in names])
        hazards = [float(row[1]) for row in model.predict_proba(rows)]
        if any(not math.isfinite(h) or not 0 <= h <= 1 for h in hazards):
            raise ValueError('Invalid model probabilities')
        probability = 1 - math.prod(1 - h for h in hazards)
        calculation={'status':'NOT_PROVIDED','dscr':None,'fees_rub':None}
        if bundle.cashflow_scenario is not None:
            scenario=bundle.cashflow_scenario
            schedule=annuity_schedule(bundle.features['requested_amount'],bundle.features['annual_rate'],int(bundle.features['term_months']))
            new_payment=Decimal(schedule[0]['payment'])
            debt_service=scenario.existing_debt_service_monthly_rub+new_payment
            calculation={'status':'ILLUSTRATIVE_EXPLICIT_INPUTS','formula_version':'DSCR_EXPLICIT_MONTHLY_1',
                         'basis_version':scenario.basis_version,'source_ref':scenario.source_ref,
                         'monthly_payment_rub':str(new_payment),'cfads_monthly_rub':str(scenario.cfads_monthly_rub),
                         'existing_debt_service_monthly_rub':str(scenario.existing_debt_service_monthly_rub),
                         'dscr':str(scenario.cfads_monthly_rub/debt_service) if debt_service else None,
                         'stress_dscr':[str(value/debt_service) if debt_service else None for value in scenario.stress_cfads_monthly_rub],
                         'interest_total_rub':str(sum(Decimal(row['interest']) for row in schedule)),
                         'fees_rub':[str(fee) for fee in scenario.fees_rub] if scenario.fees_rub is not None else None,
                         'threshold_applied':None,'is_binding':False}
        return {'status':'DEMO_ESTIMATE', 'model_id':entry['model_id'], 'model_sha256':entry['sha256'],
                'registry_version':self.registry['version'], 'feature_schema_version':bundle.schema_version,
                'source_ref':bundle.source_ref, 'target':entry['target'], 'horizon_months':months,
                'feature_input':bundle.model_dump(mode='json'),
                'calculation':calculation,
                'kind':'CUMULATIVE_PD' if bundle.kind == 'baseline' else 'ONE_MONTH_HAZARD',
                'probability':probability, 'hazards':hazards, 'calibrator':entry['calibrator'],
                'validated_for_real_lending':False, 'is_binding':False,
                'reasons':['SYNTHETIC_MODEL_REQUIRES_MANUAL_REVIEW']}


def annuity_schedule(amount, annual_rate_fraction, months):
    """Pure contractual calculation; all inputs must be explicitly supplied in an offer."""
    principal, rate = Decimal(str(amount)), Decimal(str(annual_rate_fraction))
    if not principal.is_finite() or principal <= 0 or not rate.is_finite() or not 0 <= rate <= 1 or type(months) is not int or not 1 <= months <= 600:
        raise ValueError('Invalid explicit payment parameters')
    cent = Decimal('0.01')
    principal = principal.quantize(cent, rounding=ROUND_HALF_UP)
    monthly = rate / 12
    payment = (principal / months if monthly == 0 else principal * monthly / (1 - (1 + monthly) ** -months)).quantize(cent, rounding=ROUND_HALF_UP)
    balance, rows = principal, []
    for month in range(1, months + 1):
        interest = (balance * monthly).quantize(cent, rounding=ROUND_HALF_UP)
        due_principal = balance if month == months else min(balance, payment - interest)
        rows.append({'month':month, 'principal':str(due_principal), 'interest':str(interest),
                     'payment':str(due_principal + interest), 'balance':str(balance - due_principal)})
        balance -= due_principal
    return rows
