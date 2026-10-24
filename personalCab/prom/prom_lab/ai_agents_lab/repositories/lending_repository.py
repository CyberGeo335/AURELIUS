"""Persistent M4/M5 DEMO application services; manual underwriting is authoritative.

Borrowers cannot approve features, product rules or their own applications.
Reviewer methods are exposed only by the trusted operator CLI.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..services.assessment import AssessmentService, annuity_schedule
from ..schemas.lending import DemoOffer
from ..services.identifiers import stable_hash
from ..repositories.case_repository import AccessDenied, ConflictError


class LendingRepository:
    def __init__(self, config, assessment_service=None):
        self.config = config
        self.assessment_service = assessment_service or AssessmentService()

    @staticmethod
    def scoped_case(db, envelope):
        row = db.execute('SELECT payload FROM credit_cases WHERE case_id=%s', (envelope['case_id'],)).fetchone()
        case = json.loads(row['payload']) if row else None
        if not case or (case['owner_id'], case['request']['borrower_id'], case.get('company_id'), case['revision']) != (
                envelope['owner_id'], envelope['borrower_id'], envelope['company_id'], envelope['revision']):
            raise AccessDenied('CASE_SCOPE_MISMATCH')
        return case

    @staticmethod
    def route(envelope, product_code):
        if product_code not in envelope.get('data_context', {}).get('application_ids', {}):
            raise ValueError('Product must have a current evidence snapshot')
        return envelope['data_context']['application_ids'][product_code]

    def run_assessment(self, envelope, arguments):
        code = arguments.get('product_code', 'R01')
        application_id = self.route(envelope, code)
        evidence_ref = envelope['result_refs']['evidence']
        with self.config.connect(workflow=True) as db:
            self.scoped_case(db, envelope)
            source = db.execute('SELECT data FROM feature_inputs WHERE case_id=%s AND revision=%s AND evidence_ref=%s AND product_code=%s',
                                (envelope['case_id'],envelope['revision'],evidence_ref,code)).fetchone()
        features = source['data'] if source else None
        horizon = arguments.get('horizon_months', 12)
        digest = stable_hash([features, envelope['request'], evidence_ref, horizon, self.assessment_service.registry])
        with self.config.connect(workflow=True) as db:
            existing = db.execute('SELECT data FROM assessments WHERE case_id=%s AND revision=%s AND product_code=%s AND input_hash=%s',
                                  (envelope['case_id'],envelope['revision'],code,digest)).fetchone()
        if existing:
            return existing['data']
        result = self.assessment_service.assess(features, product_code=code, request=envelope['request'], horizon=horizon)
        result.update(assessment_id='ASSESS-'+uuid4().hex, case_id=envelope['case_id'], revision=envelope['revision'],
                      company_id=envelope['company_id'], product_code=code, application_id=application_id,
                      evidence_ref=evidence_ref, snapshot_ids=envelope['data_context']['snapshot_ids'],feature_input_hash=stable_hash(features))
        with self.config.connect(workflow=True) as db:
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (envelope['case_id'],))
            self.scoped_case(db, envelope)
            existing = db.execute('SELECT data FROM assessments WHERE case_id=%s AND revision=%s AND product_code=%s AND input_hash=%s',
                                  (envelope['case_id'],envelope['revision'],code,digest)).fetchone()
            if existing:
                return existing['data']
            scoring_id = None
            if result['status'] == 'DEMO_ESTIMATE':
                # Public pd is intentionally null for one-month dynamic hazard.
                pd = result['probability'] if result['kind'] == 'CUMULATIVE_PD' else None
                scoring_id = db.execute("INSERT INTO public.scoring_results(application_id,model_version,pd,risk_grade,feature_snapshot,source_snapshot_date) VALUES(%s,%s,%s,'UNRATED',%s,%s) RETURNING scoring_result_id",
                                        (application_id,result['model_id'],pd,Jsonb(result),envelope['decision_at'])).fetchone()['scoring_result_id']
            result['scoring_result_id'] = scoring_id
            db.execute('INSERT INTO assessments(assessment_id,case_id,revision,evidence_ref,product_code,input_hash,data,scoring_result_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                       (result['assessment_id'],envelope['case_id'],envelope['revision'],evidence_ref,code,digest,Jsonb(result),scoring_id))
        return result

    def submit_application(self, envelope, arguments):
        code = arguments.get('product_code', 'R01')
        application_id = self.route(envelope,code)
        assessment = envelope.get('assessment')
        if not assessment or assessment['product_code'] != code or assessment['evidence_ref'] != envelope['result_refs']['evidence']:
            raise ValueError('Current assessment required; insufficient data may be submitted for manual review')
        with self.config.connect(workflow=True) as db:
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (envelope['case_id'],))
            self.scoped_case(db,envelope)
            current_input=db.execute('SELECT data FROM feature_inputs WHERE case_id=%s AND revision=%s AND evidence_ref=%s AND product_code=%s FOR SHARE',
                                     (envelope['case_id'],envelope['revision'],envelope['result_refs']['evidence'],code)).fetchone()
            if assessment.get('feature_input_hash')!=stable_hash(current_input['data'] if current_input else None):
                raise ConflictError('Reviewed inputs changed; run assessment again before submission')
            existing = db.execute('SELECT data FROM lender_cases WHERE case_id=%s AND revision=%s AND product_code=%s',
                                  (envelope['case_id'],envelope['revision'],code)).fetchone()
            if existing:
                if existing['data']['evidence_ref'] != envelope['result_refs']['evidence'] or existing['data']['assessment_id']!=assessment['assessment_id']:
                    raise ConflictError('Existing review uses older evidence or assessment; refresh to start a revised request')
                return existing['data']
            result = {'lender_case_id':'DEMO-'+uuid4().hex, 'status':'MANUAL_REVIEW', 'mode':'DEMO',
                      'case_id':envelope['case_id'], 'revision':envelope['revision'], 'product_code':code,
                      'application_id':application_id, 'assessment_id':assessment['assessment_id'],
                      'evidence_ref':envelope['result_refs']['evidence'], 'offer':None, 'is_binding':False,
                      'execution':None, 'review_reasons':['MANUAL_DECISION_REQUIRED'], 'version':1}
            changes=db.execute("SELECT field_code,old_value,new_value,changed_at FROM client_field_changes WHERE case_id=%s AND product_code=%s AND review_status='PENDING' ORDER BY change_id",(envelope['case_id'],code)).fetchall()
            result['client_changes']=envelope.get('client_changes',[])+[{**row,'changed_at':row['changed_at'].isoformat()} for row in changes]
            if result['client_changes']:
                result['review_reasons'].append('CLIENT_DATA_CHANGED_CHECK_REGISTRIES')
            db.execute('INSERT INTO lender_cases(lender_case_id,case_id,revision,product_code,evidence_ref,data) VALUES(%s,%s,%s,%s,%s,%s)',
                       (result['lender_case_id'],envelope['case_id'],envelope['revision'],code,result['evidence_ref'],Jsonb(result)))
            db.execute("INSERT INTO public.credit_decisions(application_id,scoring_result_id,policy_version,eligibility_status,decision,reasons) VALUES(%s,%s,'DEMO-MANUAL-1','NEEDS_DATA','MANUAL_REVIEW',%s)",
                       (application_id,assessment.get('scoring_result_id'),Jsonb(result['review_reasons'])))
            self.event(db,result,'SUBMITTED',envelope['owner_id'])
        return result

    @staticmethod
    def event(db, result, action, actor):
        db.execute('INSERT INTO lender_events(event_id,lender_case_id,event_type,actor_id,data) VALUES(%s,%s,%s,%s,%s)',
                   ('EV-'+uuid4().hex,result['lender_case_id'],action,actor,Jsonb(result)))

    @staticmethod
    def save(db, result):
        result['version'] += 1
        db.execute('UPDATE lender_cases SET data=%s,version=%s WHERE lender_case_id=%s',
                   (Jsonb(result),result['version'],result['lender_case_id']))

    @staticmethod
    def check_assessment_inputs(db,result):
        assessed=db.execute('SELECT data FROM assessments WHERE assessment_id=%s',(result['assessment_id'],)).fetchone()
        current=db.execute('SELECT data FROM feature_inputs WHERE case_id=%s AND revision=%s AND evidence_ref=%s AND product_code=%s FOR SHARE',
                           (result['case_id'],result['revision'],result['evidence_ref'],result['product_code'])).fetchone()
        if not assessed or assessed['data'].get('feature_input_hash')!=stable_hash(current['data'] if current else None):
            raise ConflictError('Reviewed inputs changed after assessment; a new assessment/review is required')

    def get_bank_status(self, envelope, arguments):
        ref = envelope['result_refs'].get('bank_application')
        with self.config.connect(workflow=True) as db:
            self.scoped_case(db,envelope)
            row = db.execute('SELECT data FROM lender_cases WHERE lender_case_id=%s AND case_id=%s AND revision=%s',
                             (ref,envelope['case_id'],envelope['revision'])).fetchone()
            if not row:
                raise AccessDenied('LENDER_CASE_NOT_FOUND')
            return row['data']

    def review(self, lender_case_id, *, reviewer, decision, reason, offer=None):
        if not reviewer.strip() or not reason.strip() or decision not in {'OFFERED','DECLINED','REQUEST_DATA'}:
            raise ValueError('Explicit operator, decision and reason required')
        checked_offer = DemoOffer.model_validate(offer) if decision == 'OFFERED' else None
        with self.config.connect(workflow=True) as db:
            row = db.execute('SELECT data FROM lender_cases WHERE lender_case_id=%s FOR UPDATE',(lender_case_id,)).fetchone()
            if not row:
                raise KeyError('Application not found')
            result = row['data']
            current = db.execute('SELECT payload FROM credit_cases WHERE case_id=%s',(result['case_id'],)).fetchone()
            case = json.loads(current['payload'])
            if case['revision'] != result['revision'] or case['result_refs'].get('evidence') != result['evidence_ref'] or case['status'] in {'CANCELLED','COMPLETED'}:
                raise ConflictError('Application revision is no longer current')
            if case['result_refs'].get('assessment')!=result['assessment_id']:
                raise ConflictError('Assessment changed during manual review')
            self.check_assessment_inputs(db,result)
            if result['status'] not in {'MANUAL_REVIEW','REQUEST_DATA'}:
                raise ConflictError('Application already reviewed')
            if checked_offer:
                if (result['product_code']=='R01') != (checked_offer.repayment_type=='ANNUITY'):
                    raise ValueError('Only R01 annuity and R02/R03 limit opening are supported')
                result['offer'] = checked_offer.model_dump(mode='json')
                result['offer']['offer_id'] = 'OFFER-'+uuid4().hex
                result['offer']['schedule'] = annuity_schedule(checked_offer.amount_rub,checked_offer.annual_rate_fraction,checked_offer.term_months) if checked_offer.repayment_type=='ANNUITY' else []
                result['offer']['is_binding'] = False
                result['offer']['assessment_matches_offer']=(checked_offer.amount_rub==Decimal(str(case['request']['amount_rub'])) and checked_offer.term_months==case['request']['term_months'])
            result.update(status=decision,review_reasons=[reason],reviewed_by=reviewer)
            public_decision = {'OFFERED':'APPROVE','DECLINED':'REJECT','REQUEST_DATA':'REQUEST_DATA'}[decision]
            db.execute('INSERT INTO public.credit_decisions(application_id,policy_version,eligibility_status,decision,approved_amount,reasons) VALUES(%s,%s,%s,%s,%s,%s)',
                       (result['application_id'],'DEMO-MANUAL-1','NEEDS_DATA' if decision=='REQUEST_DATA' else 'ELIGIBLE' if decision=='OFFERED' else 'INELIGIBLE',public_decision,
                        checked_offer.amount_rub if checked_offer else None,Jsonb({'mode':'DEMO','reviewer':reviewer,'reason':reason})))
            self.save(db,result)
            self.event(db,result,'REVIEWED',reviewer)
        return result

    def borrower_action(self, envelope, arguments, *, execute=False):
        if arguments.get('acknowledge_demo') is not True:
            raise ValueError('Explicit DEMO acknowledgement required')
        with self.config.connect(workflow=True) as db:
            self.scoped_case(db,envelope)
            ref = envelope['result_refs'].get('bank_application')
            row = db.execute('SELECT data FROM lender_cases WHERE lender_case_id=%s AND case_id=%s AND revision=%s FOR UPDATE',
                             (ref,envelope['case_id'],envelope['revision'])).fetchone()
            if not row:
                raise AccessDenied('LENDER_CASE_NOT_FOUND')
            result = row['data']
            if result['evidence_ref'] != envelope['result_refs'].get('evidence'):
                raise ConflictError('Evidence changed after submission')
            if result['assessment_id'] != envelope['result_refs'].get('assessment'):
                raise ConflictError('Assessment changed after submission')
            offer = result.get('offer')
            if not offer or arguments.get('offer_id') != offer['offer_id']:
                raise ConflictError('Explicit current offer selection required')
            if result['status']=='EXECUTED_DEMO' or (not execute and result['status']=='ACCEPTED'):
                return result
            self.check_assessment_inputs(db,result)
            if datetime.fromisoformat(offer['expires_at']) <= datetime.now(timezone.utc):
                raise ConflictError('Offer expired')
            expected = 'ACCEPTED' if execute else 'OFFERED'
            if result['status'] != expected:
                raise ConflictError('Action is invalid at the current stage')
            if execute:
                result['status'] = 'EXECUTED_DEMO'
                result['execution'] = {'operation_id':'SIM-'+uuid4().hex,'confirmed':True,'simulated':True,
                                       'kind':'DISBURSEMENT' if offer['repayment_type']=='ANNUITY' else 'LIMIT_OPENED',
                                       'amount_rub':offer['amount_rub'] if offer['repayment_type']=='ANNUITY' else '0',
                                       'credit_limit_rub':offer['amount_rub'] if offer['repayment_type']=='LIMIT_ONLY' else None,
                                       'executed_at':datetime.now(timezone.utc).isoformat()}
            else:
                result['status'] = 'ACCEPTED'
                result['acceptance'] = {'actor_id':envelope['owner_id'],'accepted_at':datetime.now(timezone.utc).isoformat(),
                                        'offer_id':offer['offer_id'],'acknowledge_demo':True,'is_legal_signature':False}
            self.save(db,result)
            self.event(db,result,'EXECUTED_DEMO' if execute else 'ACCEPTED',envelope['owner_id'])
        return result

    def accept_offer(self,envelope,arguments):
        return self.borrower_action(envelope,arguments)

    def execute_demo(self,envelope,arguments):
        return self.borrower_action(envelope,arguments,execute=True)

    def record_demo_payment(self,case,actor,operation_id,amount):
        """Simulate schedule settlement only, never a bank transfer or a default label."""
        from ..repositories.case_repository import check_access
        from ..schemas.models import Scope
        check_access(case,actor)
        if not actor.has_consent(Scope.DEMO_EXECUTION,case.request.borrower_id):
            raise AccessDenied('CONSENT_REQUIRED')
        value=Decimal(str(amount))
        if not value.is_finite() or value<=0 or value!=value.quantize(Decimal('0.01')):
            raise ValueError('A positive amount with at most two decimal places is required')
        with self.config.connect(workflow=True) as db:
            row=db.execute('SELECT data FROM lender_cases WHERE lender_case_id=%s AND case_id=%s AND revision=%s FOR UPDATE',
                           (case.result_refs.get('bank_application'),case.case_id,case.revision)).fetchone()
            if not row:
                raise AccessDenied('LENDER_CASE_NOT_FOUND')
            result=row['data']
            if result['status']!='EXECUTED_DEMO' or result['offer']['repayment_type']!='ANNUITY':
                raise ConflictError('An executed DEMO annuity schedule is required')
            payments=result.setdefault('payments',[])
            existing=next((item for item in payments if item['operation_id']==operation_id),None)
            if existing:
                if Decimal(existing['amount_rub'])!=value:
                    raise ConflictError('Payment operation ID reused with a different amount')
                return result
            # Fees are disclosed separately; their due dates are not inferred.
            if any(Decimal(fee)!=0 for fee in result['offer']['fees_rub']):
                raise ValueError('Fee settlement needs an explicit schedule; simulation is limited to zero-fee offers')
            total=sum(Decimal(item['payment']) for item in result['offer']['schedule'])
            paid=sum(Decimal(item['amount_rub']) for item in payments)
            if paid+value>total:
                raise ValueError('Payment exceeds remaining scheduled amount')
            payments.append({'operation_id':operation_id,'amount_rub':str(value),'recorded_at':datetime.now(timezone.utc).isoformat(),'simulated':True})
            remaining_credit=paid+value
            settlement=[]
            for installment in result['offer']['schedule']:
                due=Decimal(installment['payment'])
                allocated=min(remaining_credit,due)
                remaining_credit-=allocated
                settlement.append({'month':installment['month'],'scheduled_rub':str(due),'paid_rub':str(allocated),'remaining_rub':str(due-allocated)})
            result['servicing']={'kind':'DEMO_SCHEDULE_ORDER_V1','settlement':settlement,
                                 'remaining_scheduled_rub':str(total-paid-value),'closed':total==paid+value,
                                 'no_real_money':True,'default_label_created':False}
            self.save(db,result)
            self.event(db,result,'PAYMENT_SIMULATED',actor.actor_id)
        return result
