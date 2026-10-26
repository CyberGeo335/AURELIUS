"""Application-scoped reported model inputs for the explicitly marked DEMO.

Never update companies or mark a customer answer verified. Production keeps
requiring its independently reviewed company profile.
"""
import re
from datetime import date

from .database import _rows
from .schemas import InputError


def application_company(connection, application, company, as_of, *, demo_only):
    profile, provenance = dict(company), {}
    if not demo_only:
        return profile, provenance
    answers = _rows(connection, """SELECT v.field_code,v.field_value,v.value_source,
        v.verification_status,v.source_reference,v.obtained_at,r.target_db_field
        FROM public.application_field_values v
        JOIN public.application_field_requirements r
          ON r.field_code=v.field_code AND r.product_code=v.product_code
        JOIN public.application_details d ON d.application_id=v.application_id
        WHERE v.application_id=:id AND v.product_code=:product
          AND d.confirmed_at IS NOT NULL AND d.confirmed_at < CAST(:cutoff AS date) + INTERVAL '1 day'
          AND v.obtained_at < CAST(:cutoff AS date) + INTERVAL '1 day'""",
        id=application['application_id'], product=application['product_code'], cutoff=as_of)
    for answer in answers:
        target = answer['target_db_field'].removeprefix('public.').split(' + ')[0]
        field = target.removeprefix('companies.')
        if target not in {'companies.registration_date', 'companies.okved_main'}:
            continue
        raw = answer['field_value']
        if raw in (None, ''):
            continue
        if not isinstance(raw, str):
            raise InputError(f'Invalid reported {field}: {answer["field_code"]}')
        if field == 'registration_date':
            try:
                value = date.fromisoformat(raw)
            except ValueError as exc:
                raise InputError('Invalid reported registration_date') from exc
            if value > as_of:
                raise InputError('Reported registration_date is after assessment cutoff')
        else:
            if not re.fullmatch(r'[0-9]{2}(?:\.[0-9]{1,2}){0,2}', raw):
                raise InputError('Invalid reported main OKVED')
            value = raw
        existing = profile.get(field)
        if existing not in (None, ''):
            if str(existing) != str(value):
                raise InputError(f'Reported {field} conflicts with company profile; employee review required')
            continue
        if field in provenance and profile[field] != value:
            raise InputError(f'Conflicting application answers for {field}')
        profile[field] = value
        provenance[field] = {
            'source_ref': f'application_field_values:{application["application_id"]}:{answer["field_code"]}',
            'company_id': company['company_id'], 'application_id': application['application_id'],
            'value_source': answer['value_source'], 'verification_status': answer['verification_status'],
            'available_at': answer['obtained_at'].isoformat(), 'demo_only': True,
        }
    return profile, provenance
