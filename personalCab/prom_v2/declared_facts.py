"""Literal, labelled current-message facts; never registry or identity verification."""
from copy import deepcopy
import re

COMPANY_TARGETS = {
    'inn': 'companies.inn', 'company_name': 'companies.name',
    'ogrn': 'companies.ogrn', 'ogrnip': 'companies.ogrnip',
    'legal_address': 'companies.legal_address', 'director_name': 'companies.director_name',
    'okved_main': 'companies.okved_main', 'registration_date': 'companies.registration_date',
    'actual_activity_description': 'companies.actual_activity_description',
    'legal_form': 'companies.legal_form',
}


def declared_facts(raw, text):
    """Fill omitted literal fields before the same Pydantic/evidence validation.

    Free prose remains the model's task. No facts from history or inferred age,
    legal form from names, identifiers, consents or financial ratios are added.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get('patch'), dict):
        return raw
    result = deepcopy(raw)
    evidence = result.setdefault('evidence', {})
    if not isinstance(evidence, dict):
        return result
    labels = {
        'company_name': r'полное наименование организации',
        'ogrn': r'\bОГРН', 'ogrnip': r'\bОГРНИП',
        'legal_address': r'юридический адрес', 'director_name': r'ФИО руководителя',
        'okved_main': r'основной ОКВЭД',
        'registration_date': r'дата государственной регистрации',
        'actual_activity_description': r'фактический вид деятельности',
        'legal_form': r'форма бизнеса',
    }
    end = r'(?=[.;]\s+(?:Мой|Моя|Форма|Цель|ИНН)\b|[;\n]|$)'
    for field, label in labels.items():
        matches = list(re.finditer(label + r'\s*[:=—-]\s*(.+?)' + end, text, re.IGNORECASE))
        values = {match.group(1).strip().rstrip('.') for match in matches}
        if len(values) != 1:
            continue
        value = values.pop()
        if field == 'legal_form':
            value = {'ООО': 'OOO', 'ИП': 'IP', 'АО': 'AO'}.get(value.upper())
        existing = result['patch'].get(field)
        if value is not None and (existing is None or type(existing) is type(value) and existing == value):
            result['patch'][field] = value
            evidence[field] = matches[0].group(0)
    # An omitted digit amount/term is recoverable without interpreting free prose.
    for field, pattern in {
        'amount_rub': r'(?<![\w.,-])([0-9][0-9 \u00a0]*)\s+руб(?:лей|ля|ль)?\b',
        'term_months': r'\bна\s+([0-9]+)\s+месяц(?:ев|а)?\b',
    }.items():
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if field == 'term_months' and re.search(r'транш|выборк', text, re.IGNORECASE):
            continue
        value = int(re.sub(r'\s', '', matches[0].group(1))) if len(matches) == 1 else None
        existing = result['patch'].get(field)
        if value is not None and (existing is None or type(existing) is type(value) and existing == value):
            result['patch'][field] = value
            evidence[field] = matches[0].group(0)
    purchase = re.search(r'\bразов\w*\s+закуп\w*', text, re.IGNORECASE)
    if purchase and not re.search(r'\bне\s+разов|регуляр|повтор', text, re.IGNORECASE):
        for field, value in {'recurring': False, 'financing_need': 'ONE_TIME_PURCHASE'}.items():
            existing = result['patch'].get(field)
            if existing is None or type(existing) is type(value) and existing == value:
                result['patch'][field] = value
                evidence[field] = purchase.group(0)
    return result
