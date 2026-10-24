"""Addressed M3 questionnaire. Reported answers never become verified facts."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

REQUEST_TARGETS = {
    'requested_amount':'amount_rub', 'requested_term_months':'term_months', 'purpose':'purpose',
}


def applicable(requirement, legal_form):
    return bool(requirement['required_ip']) if legal_form == 'IP' else bool(requirement['required_ooo']) if legal_form == 'OOO' else True


def validate_answer(value, type_name, target='', legal_form=None):
    """Validate against the actual destination SQL type, without executing format_rule text."""
    if value is None or isinstance(value,(dict,list)) or (isinstance(value,str) and (not value.strip() or len(value)>12000)):
        raise ValueError('A nonempty scalar answer is required')
    if type_name in {'integer','bigint','smallint'}:
        if type(value) is not int:
            raise ValueError('An integer is required')
    elif type_name in {'numeric','real','double precision'}:
        if type(value) not in (int,float,str):
            raise ValueError('A numeric value is required')
        try:
            if not Decimal(str(value)).is_finite():
                raise ValueError('A finite number is required')
        except InvalidOperation as exc:
            raise ValueError('A numeric value is required') from exc
    elif type_name == 'boolean':
        if type(value) is not bool:
            raise ValueError('A boolean is required')
    elif type_name in {'date','timestamp with time zone','timestamp without time zone'}:
        if type(value) is not str:
            raise ValueError('An ISO date is required')
        (date.fromisoformat if type_name=='date' else datetime.fromisoformat)(value)
    elif not isinstance(value,str):
        raise ValueError('A text value is required')
    column=target.removeprefix('public.').split('.')[-1]
    lengths={'inn':(12,) if legal_form=='IP' else (10,) if legal_form in {'OOO','AO'} else (10,12),
             'ogrn':(13,), 'ogrnip':(15,), 'kpp':(9,), 'counterparty_inn':(10,12)}
    if column in lengths:
        allowed=lengths[column]
        if not isinstance(value,str) or not re.fullmatch(r'[0-9]+',value) or len(value) not in allowed:
            raise ValueError(f'{column.upper()}: укажите только цифры, длина — '+ ' или '.join(map(str,allowed)))
    return value


def build_questionnaire(envelope,raw,requirements,values):
    result=[]
    codes = {route.get('product_id') for route in envelope['product_routes']}
    from ..repositories.business_repository import PRODUCT_CODES
    allowed={PRODUCT_CODES[code] for code in codes if code in PRODUCT_CODES}
    for field in requirements:
        code=field['product_code']
        if code not in allowed or not applicable(field,envelope['request'].get('legal_form')):
            continue
        target=field['target_db_field'].removeprefix('public.')
        table,sep,column=target.partition('.')
        reported=values.get((code,field['field_code']))
        inn_revision=max((change['revision'] for change in envelope.get('client_changes',[]) if change['field']=='inn'),default=0)
        request_inn_current=(target=='companies.inn' and envelope['request'].get('inn') and
                             (not reported or inn_revision>reported.get('reported_revision',0)))
        value,source,status=None,None,'MISSING'
        if table=='credit_applications' and column=='product_code':
            value,source,status=code,'SYSTEM','PRESENT'
        elif table=='credit_applications' and column in REQUEST_TARGETS:
            value=envelope['request'].get(REQUEST_TARGETS[column]);source='CLIENT'
            status='REPORTED' if value is not None else 'MISSING'
        elif request_inn_current:
            value,source,status=envelope['request']['inn'],'CLIENT','REPORTED'
        elif reported and reported.get('field_value') is not None:
            value,source=reported['field_value'],reported.get('value_source')
            status='VERIFIED' if reported.get('verification_status')=='VERIFIED' else 'REPORTED'
        elif table=='companies' and raw['company'].get('source_checked_at') and datetime.fromisoformat(raw['company']['source_checked_at'])<=datetime.fromisoformat(envelope['decision_at']):
            value=raw['company'].get(column);source='DATABASE'
            status='PRESENT_UNVERIFIED' if value is not None else 'MISSING'
        result.append({'product_code':code,'field_code':field['field_code'],'label':field['field_label'],
                       'target':target,'format_rule':field.get('format_rule'),'status':status,'value':value,
                       'data_type':field.get('data_type','text'),
                       'editable':not (table=='credit_applications' and column in {*REQUEST_TARGETS,'product_code'}),
                       'source_application_id':reported.get('application_id') if reported else None,
                       'source':source,'required':True,
                       'review_required':source=='CLIENT' and status=='REPORTED',
                       'question':f"{field['field_label']} ({code})" if status=='MISSING' else None})
    return result
