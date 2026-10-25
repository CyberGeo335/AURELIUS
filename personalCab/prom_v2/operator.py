"""Trusted V2 reviewer boundary. Never exposed to borrower credentials."""
from personalCab.prom.prom_lab.ai_agents_lab.repositories.operator_repository import approve_features, verify_field
from .integration import service_case
from .repository import AccessDenied, Conflict
from .models import FollowUp, utcnow
from pathlib import PurePath
from datetime import datetime


def follow_up(business, case, arguments):
    fields,documents=arguments.get('requested_fields',[]),arguments.get('requested_documents',[])
    if not isinstance(fields,list) or not all(isinstance(f,str) for f in fields) or not isinstance(documents,list) or not all(isinstance(d,str) for d in documents):
        raise ValueError('Explicit field/document lists required')
    available={q['field_code'] for q in (business.current_data(case) or {}).get('questionnaire',[]) if q['editable']}
    if set(fields)-available or any(not d.strip() or len(d)>255 or PurePath(d).name!=d or '/' in d or '\\' in d for d in documents):
        raise ValueError('Follow-up targets are not in scope')
    request=FollowUp(fields=list(dict.fromkeys(fields)),documents=list(dict.fromkeys(documents)),reason=arguments['reason'],due_at=arguments.get('due_at'))
    if request.due_at and request.due_at<=utcnow():raise ValueError('Future deadline required')
    return request


def execute(config, business, account, case, action, arguments):
    if account['role']!='OPERATOR': raise AccessDenied('OPERATOR_REQUIRED')
    if action=='claim':
        if case.review_owner not in {None,account['login']}:raise Conflict('ASSIGNED_TO_ANOTHER_REVIEWER')
        case.review_owner=account['login']
        return {'review_owner':case.review_owner}
    if action=='release':
        if case.review_owner!=account['login']:raise Conflict('NOT_ASSIGNED_TO_YOU')
        case.review_owner=None
        return {'review_owner':None}
    if case.status in {'CANCELLED','DECLINED','ACCEPTED','EXECUTED_DEMO'}:
        raise Conflict('CASE_CLOSED_FOR_REVIEW')
    if action=='authority':
        if set(arguments)!={'verified','source_ref','available_at'} or type(arguments['verified']) is not bool or not isinstance(arguments['source_ref'],str) or not arguments['source_ref'].strip():
            raise ValueError('Explicit authority evidence required')
        available=datetime.fromisoformat(arguments['available_at'])
        if available.tzinfo is None or available>utcnow():raise ValueError('Source not available')
        case.authority_evidence={**arguments,'reviewed_by':account['login'],'reviewed_at':utcnow().isoformat()}
        return {'saved':True}
    if action=='profile_resolution':
        from personalCab.prom.prom_lab.ai_agents_lab.repositories.operator_repository import resolve_profile
        return {'resolution_id':resolve_profile(config,case.company_id,arguments,account['login'])}
    if case.evidence_stale:
        raise Conflict('EVIDENCE_REFRESH_REQUIRED')
    if action=='review_changes':
        fields=arguments.get('fields')
        source=arguments.get('source_ref')
        available={c['field'] for c in case.client_changes}
        if not isinstance(fields,list) or not fields or not all(isinstance(f,str) and f in available for f in fields) or not isinstance(source,str) or not source.strip():
            raise ValueError('Explicit changed fields and source required')
        for change in case.client_changes:
            if change['field'] in fields:
                change.update(review_status='REVIEWED',reviewed_by=account['login'],source_ref=source)
        return {'saved':True}
    business.shadow(case)
    code={'term':'R01','rcl':'R02','overdraft':'R03'}[case.selected_product_id]
    if action=='features':
        return {'input_id':approve_features(config,case.case_id,code,arguments,account['login'])}
    if action=='verify':
        verify_field(config,case.case_id,code,arguments['field_code'],
                     {'value':arguments['value'],'source_ref':arguments['source_ref']},account['login'])
        with config.connect(workflow=True) as db:
            from psycopg.types.json import Jsonb
            db.execute("UPDATE client_field_changes SET review_status=CASE WHEN new_value=%s THEN 'REVIEWED' ELSE 'SUPERSEDED' END, reviewed_by=%s,source_ref=%s WHERE case_id=%s AND product_code=%s AND field_code=%s AND review_status='PENDING'",(Jsonb(arguments['value']),account['login'],arguments['source_ref'],case.case_id,code,arguments['field_code']))
        return {'saved':True}
    if action=='review':
        if not case.bank_application: raise Conflict('SUBMISSION_REQUIRED')
        request = None
        if arguments['decision'] == 'REQUEST_DATA':
            request=follow_up(business,case,arguments)
        result = business.modules.lending.review(case.bank_application['lender_case_id'],reviewer=account['login'],
                                              decision=arguments['decision'],reason=arguments['reason'],offer=arguments.get('offer'))
        if request:
            for previous in case.follow_ups:
                if previous.status=='OPEN': previous.status='SUPERSEDED'
            case.follow_ups.append(request)
        if result.get('offer'):
            case.offer_history.append({'offer':result['offer'],'revision':case.revision,
                                       'reviewed_by':account['login'],'created_at':utcnow().isoformat(),
                                       'invalidated_at':None})
        return result
    raise ValueError('Unknown operator action')
