"""Server projections and read-only decision preview; no mock financial policy."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from personalCab.prom.prom_lab.ai_agents_lab.schemas.lending import DemoOffer
from personalCab.prom.prom_lab.ai_agents_lab.services.assessment import annuity_schedule


def statement_coverage(extracted, cutoff):
    """Declare observed month coverage only. Never turn a file into verified turnover."""
    months, conflicts, issues = {}, set(), []
    recognized = False
    for table in extracted.get('tables', []):
        rows = table.get('rows', [])
        if not rows:
            continue
        headers = [str(v or '').strip().lower() for v in rows[0]]
        if 'month' not in headers or 'incoming_rub' not in headers:
            continue
        recognized = True
        mi, ai = headers.index('month'), headers.index('incoming_rub')
        for row in rows[1:]:
            if not any(v is not None and str(v).strip() for v in row):
                continue
            try:
                month = str(row[mi]).strip()
                if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
                    raise ValueError()
                amount = Decimal(str(row[ai]).strip())
                if not amount.is_finite() or amount < 0:
                    raise ValueError()
                # A current partial month is shown, never counted as a complete period.
                if month > cutoff.strftime('%Y-%m'):
                    issues.append('FUTURE_PERIOD:'+month)
                    continue
                if month in months:
                    conflicts.add(month)
                else:
                    months[month] = str(amount)
            except (ValueError, TypeError, IndexError, InvalidOperation):
                issues.append('INVALID_STATEMENT_ROW')
    index = cutoff.year * 12 + cutoff.month - 1
    expected = [f'{(index-i)//12:04d}-{(index-i)%12+1:02d}' for i in range(12, 0, -1)]
    present = sorted(months)
    return {'status':'CONFLICT' if conflicts or issues else 'REPORTED' if recognized else 'UNRECOGNIZED',
            'months':present, 'expected_months':expected,
            'missing_months':[m for m in expected if m not in months or m in conflicts],
            'duplicate_months':sorted(conflicts), 'issues':sorted(set(issues)),
            'covered_months':len([m for m in expected if m in months and m not in conflicts]),
            'is_verified':False, 'full_business_coverage_verified':False}


def preview_decision(case, arguments):
    decision = arguments.get('decision')
    reason = arguments.get('reason', '')
    if decision not in {'REQUEST_DATA','OFFERED','DECLINED'} or not isinstance(reason,str) or len(reason.strip()) < 15:
        raise ValueError('Explicit decision and reason required')
    result = {'decision':decision, 'reason':reason, 'case_id':case.case_id,
              'version':case.version, 'revision':case.revision, 'is_binding':False}
    if decision == 'OFFERED':
        offer = DemoOffer.model_validate(arguments.get('offer'))
        if (case.selected_product_id == 'term') != (offer.repayment_type == 'ANNUITY'):
            raise ValueError('Unsupported repayment type')
        schedule = annuity_schedule(offer.amount_rub,offer.annual_rate_fraction,offer.term_months) if offer.repayment_type=='ANNUITY' else []
        result['offer'] = {**offer.model_dump(mode='json'), 'schedule':schedule,
                           'assessment_matches_offer':offer.amount_rub==Decimal(str(case.request.amount_rub)) and offer.term_months==case.request.term_months}
    else:
        result.update({key:arguments.get(key) for key in ('requested_fields','requested_documents','due_at')})
    return result


def audit_metadata(case):
    assessment = case.assessment or {}
    return {'product_id':case.selected_product_id,
            'evidence_ref':(case.data_context or {}).get('evidence_ref'),
            'snapshot_ids':(case.data_context or {}).get('snapshot_ids'),
            'assessment_id':assessment.get('assessment_id'),
            'model_id':assessment.get('model_id'), 'model_sha256':assessment.get('model_sha256'),
            'model_horizon_months':assessment.get('horizon_months'),
            'lender_case_id':(case.bank_application or {}).get('lender_case_id'),
            'status':case.status}
