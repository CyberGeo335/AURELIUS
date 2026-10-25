import math
import pytest
from personalCab.prom_v2.assessment import ExplainableAssessmentService
from personalCab.prom.prom_lab.ai_agents_lab.services.assessment import AssessmentService
from personalCab.prom.prom_lab.ai_agents_lab.tests.test_cabinet_modules import feature_bundle


@pytest.mark.parametrize('kind',['baseline','dynamic'])
def test_real_shap_reconstructs_monthly_logit_without_changing_probability(kind):
    bundle=feature_bundle(kind)
    request={'amount_rub':3000000,'term_months':24,'legal_form':'OOO'}
    original=AssessmentService().assess(bundle,product_code='R01',request=request)
    result=ExplainableAssessmentService().assess(bundle,product_code='R01',request=request)
    assert result['probability']==original['probability'] and result['horizon_months']==original['horizon_months']
    explanation=result['explanation']
    assert explanation['status']=='AVAILABLE' and explanation['space']=='RAW_MONTHLY_LOGIT'
    assert len(explanation['contributions'])==len(bundle['features'])
    assert math.isclose(sum(c['contribution'] for c in explanation['contributions'])+explanation['base_value'],explanation['raw_output'],abs_tol=1e-7)
    monthly=1/(1+math.exp(-explanation['raw_output']))
    assert math.isclose(monthly,result['hazards'][0],abs_tol=1e-7)
    assert result['kind']==('CUMULATIVE_PD' if kind=='baseline' else 'ONE_MONTH_HAZARD')


def test_explanation_failure_is_explicit_and_preserves_real_assessment():
    service=ExplainableAssessmentService()
    def fail(result):raise RuntimeError('Synthetic attribution failure')
    service._explain=fail
    result=service.assess(feature_bundle(),product_code='R01',request={'amount_rub':3000000,'term_months':24,'legal_form':'OOO'})
    assert result['status']=='DEMO_ESTIMATE' and result['probability'] is not None
    assert result['explanation']=={'status':'UNAVAILABLE','reason':'SHAP_CALCULATION_UNAVAILABLE'}
