"""Projection and early-profile contracts independent of external services."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest

from personalCab.prom_v2.agent import Agent
from personalCab.prom_v2.models import Actor, Case, Command, Grant, LoanRequest, utcnow
from personalCab.prom_v2.repository import MemoryRepository
from personalCab.prom_v2.workspace import statement_coverage, preview_decision


def test_statement_coverage_is_relative_to_cutoff_and_never_verifies_business():
    cutoff=datetime(2026,10,25,tzinfo=timezone.utc)
    expected=[f'{2025 if i<3 else 2026}-{(i+9)%12+1:02d}' for i in range(12)]
    result=statement_coverage({'tables':[{'rows':[['month','incoming_rub'],*[[m,'123.00'] for m in expected]]}]},cutoff)
    assert result['covered_months']==12 and result['missing_months']==[]
    assert not result['is_verified'] and not result['full_business_coverage_verified']
    assert expected==result['expected_months']


@pytest.mark.parametrize('row,issue',[
    (['2026-11','3'],'FUTURE_PERIOD:2026-11'),(['2026-13','2'],'INVALID_STATEMENT_ROW'),
    (['2026-09','NaN'],'INVALID_STATEMENT_ROW'),(['2026-09','-1'],'INVALID_STATEMENT_ROW')])
def test_statement_invalid_or_future_rows_are_not_coverage(row,issue):
    result=statement_coverage({'tables':[{'rows':[['month','incoming_rub'],row]}]},datetime(2026,10,25,tzinfo=timezone.utc))
    assert result['covered_months']==0 and issue in result['issues']


def test_duplicate_statement_month_is_a_conflict_not_double_counted():
    result=statement_coverage({'tables':[{'rows':[['month','incoming_rub'],['2026-09','3'],['2026-09','3']]}]},datetime(2026,10,25,tzinfo=timezone.utc))
    assert result['status']=='CONFLICT' and result['covered_months']==0
    assert result['duplicate_months']==['2026-09']


def test_unsupported_statement_has_no_invented_months():
    result=statement_coverage({'tables':[]},utcnow())
    assert result['status']=='UNRECOGNIZED' and result['months']==[]


class ProfileModules:
    def supports(self, action):return action=='LOOKUP_PROFILE'
    def lookup_profile(self,case):
        at=case.data_cutoff_at.isoformat()
        return {'company_id':case.company_id,'borrower_id':case.borrower_id,'decision_at':at,'conflicts':[],
                'verified_facts':[{'field':'legal_form','value':'IP','company_id':case.company_id,'borrower_id':case.borrower_id,
                                   'confirmed':True,'scope':'PRODUCT_MATCHING','source_ref':'registry:synthetic:1',
                                   'verified_at':at,'available_at':at,'snapshot_as_of':at,'validity':'AS_OF_SNAPSHOT'}]}


def test_early_profile_requires_consent_and_fills_only_verified_legal_form():
    actor=Actor(actor_id='profile-test',company_id=40,borrower_id='company-40')
    agent=Agent(MemoryRepository(),modules=ProfileModules())
    def command(name,view=None):return agent.handle(actor,Command(action=name,request_id=uuid4().hex,case_id=view.case_id if view else None,expected_version=view.version if view else 0))
    view=command('CREATE')
    denied=command('LOOKUP_PROFILE',view)
    assert denied.error_code=='CONSENT_REQUIRED' and denied.request.legal_form is None
    actor.grants=[Grant(scope='EVIDENCE_COLLECTION',granted_at=utcnow()-timedelta(seconds=1),expires_at=utcnow()+timedelta(hours=1))]
    found=command('LOOKUP_PROFILE',denied)
    assert found.request.legal_form=='IP' and found.request.amount_rub is None and found.request.term_months is None
    assert found.data_resolution.database_lookup=='FOUND'
    assert found.business_profile['verified_facts'][0]['source_ref']=='registry:synthetic:1'


def test_foreign_profile_result_is_rejected_atomically():
    modules=ProfileModules()
    actual=modules.lookup_profile
    modules.lookup_profile=lambda c:{**actual(c),'company_id':41,'verified_facts':[]}
    actor=Actor(actor_id='foreign-profile',company_id=40,borrower_id='company-40',grants=[Grant(scope='EVIDENCE_COLLECTION',granted_at=utcnow()-timedelta(seconds=1),expires_at=utcnow()+timedelta(hours=1))])
    agent=Agent(MemoryRepository(),modules=modules)
    case=agent.handle(actor,Command(action='CREATE',request_id=uuid4().hex,expected_version=0))
    with pytest.raises(ValueError,match='scope mismatch'):
        agent.handle(actor,Command(action='LOOKUP_PROFILE',request_id=uuid4().hex,case_id=case.case_id,expected_version=case.version))
    assert agent.state(actor,case.case_id).version==case.version


def test_offer_preview_uses_real_schedule_and_does_not_mutate_case():
    case=Case(case_id='preview',owner_id='owner',company_id=40,borrower_id='company-40',version=3,selected_product_id='term',request=LoanRequest(borrower_id='company-40',amount_rub=3000000,term_months=24))
    before=case.model_dump()
    preview=preview_decision(case,{'decision':'OFFERED','reason':'Explicit synthetic counteroffer review',
                                 'offer':{'amount_rub':'2000000','term_months':12,'annual_rate_fraction':'0.24','repayment_type':'ANNUITY','expires_at':(utcnow()+timedelta(hours=1)).isoformat(),'conditions':['Synthetic only'],'fees_rub':['50']}})
    assert not preview['is_binding'] and not preview['offer']['assessment_matches_offer']
    assert len(preview['offer']['schedule'])==12 and preview['offer']['fees_rub']==['50']
    assert case.model_dump()==before
