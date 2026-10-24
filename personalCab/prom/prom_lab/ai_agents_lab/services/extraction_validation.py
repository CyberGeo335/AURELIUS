"""Pydantic validation per field: one invalid value must not discard valid siblings."""
import json
import re
from decimal import Decimal
from pydantic import ValidationError
from ..schemas.models import Case, Extraction, LoanRequest, explicit_control_intent
from ..schemas.resolution import FieldProblem, VerbatimEvidence


class InvalidExtraction(ValueError):
    pass


def numeric_conflict(field: str, value, quote: str) -> bool:
    """Check unambiguous digit+unit quotes; word numerals still require LLM/evals."""
    if field == 'amount_rub':
        matches = re.findall(r'(?<![\w.,])([−-]?\d[\d \u00a0]*(?:[.,]\d+)?)\s*(млн|миллион\w*|тыс\w*)?\s*(?:₽|руб\w*)', quote.casefold())
        amounts = {Decimal(number.replace(' ', '').replace('\u00a0','').replace(',','.').replace('−','-')) *
                   (1000000 if scale.startswith(('млн','миллион')) else 1000 if scale.startswith('тыс') else 1)
                   for number,scale in matches}
        return len(amounts) == 1 and Decimal(value) not in amounts
    if field == 'term_months':
        matches = re.findall(r'(?<!\w)([−-]?\d+)\s*(месяц\w*|мес\.?|год\w*|лет)', quote.casefold())
        terms = {int(number.replace('−','-')) * (12 if unit.startswith(('год','лет')) else 1) for number,unit in matches}
        return len(terms) == 1 and value not in terms
    return False


def explicit_numeric_problems(text: str) -> list[FieldProblem]:
    """An explicit invalid change still needs a question when the LLM returns null."""
    patterns = {
        'amount_rub': r'(?:измени|поменяй|замени|укажи)\s+сумму\s+(?:на\s+)?([−-]?\d[\d \u00a0]*(?:[.,]\d+)?)\s*(млн|миллион\w*|тыс\w*)?',
        'term_months': r'(?:измени|поменяй|замени|укажи)\s+срок\s+(?:на\s+)?([−-]?\d+(?:[.,]\d+)?)\s*(месяц\w*|мес\.?|год\w*|лет)?',
    }
    issues = []
    for field,pattern in patterns.items():
        for match in re.finditer(pattern, text.casefold()):
            number,unit = match.groups()
            value = Decimal(number.replace(' ', '').replace('\u00a0','').replace(',','.').replace('−','-'))
            multiplier = (1000000 if (unit or '').startswith(('млн','миллион')) else 1000 if (unit or '').startswith('тыс') else 1) if field == 'amount_rub' else (12 if (unit or '').startswith(('год','лет')) else 1)
            value *= multiplier
            candidate = int(value) if value == value.to_integral_value() else float(value)
            try:
                LoanRequest.model_validate_json(json.dumps({field:candidate}),strict=True)
            except ValidationError:
                issues.append(FieldProblem(field=field,code='INVALID_VALUE'))
    return issues


def validate_extraction(response, text: str, case: Case) -> Extraction:
    if not isinstance(response, dict) or not isinstance(response.get('patch'), dict):
        raise InvalidExtraction('Expected extraction object with patch')
    if set(response) - set(Extraction.model_fields) or set(response['patch']) - set(LoanRequest.model_fields):
        raise InvalidExtraction('Unknown extraction keys')
    evidence = response.get('evidence', {})
    if not isinstance(evidence, dict):
        raise InvalidExtraction('Expected evidence object')
    evidence = {key:value for key,value in evidence.items() if isinstance(key,str) and isinstance(value,str)}
    patch, problems = {}, []
    for field, value in response['patch'].items():
        if value is None:
            continue
        try:
            parsed = LoanRequest.model_validate_json(json.dumps({field:value}), strict=True)
        except (ValidationError, TypeError, ValueError):
            problems.append(FieldProblem(field=field, code='INVALID_VALUE'))
            continue
        if (getattr(parsed, field) == getattr(case.request, field)
                and not any(issue.field == field for issue in case.pending_clarifications)):
            continue
        quote = evidence.get(field)
        try:
            VerbatimEvidence.model_validate({'quote':quote}, context={'text':text})
        except ValidationError:
            problems.append(FieldProblem(field=field, code='MISSING_QUOTE' if not quote else 'UNGROUNDED_QUOTE'))
            continue
        if numeric_conflict(field, value, quote):
            problems.append(FieldProblem(field=field, code='UNSUPPORTED_ASSERTION'))
            continue
        if field=='inn':
            from .questionnaire import validate_answer
            try:
                validate_answer(value,'text','companies.inn',response['patch'].get('legal_form') or case.request.legal_form)
                if not re.search(r'(?<![0-9A-Za-z])'+re.escape(value)+r'(?![0-9A-Za-z])',quote):
                    raise ValueError('INN must occur verbatim')
            except ValueError:
                problems.append(FieldProblem(field=field,code='INVALID_VALUE'))
                continue
        if field == 'recurring' and not re.search(r'повтор|постоян|регуляр|ежемесяч|кажд' if value else r'разов|однократ', quote.casefold()):
            problems.append(FieldProblem(field=field, code='UNSUPPORTED_ASSERTION'))
            continue
        if field == 'financing_need' and value in {'ONE_TIME_PURCHASE', 'REPEATED_PURCHASES'} and not re.search(r'разов|однократ' if value == 'ONE_TIME_PURCHASE' else r'повтор|постоян|регуляр|ежемесяч|кажд', quote.casefold()):
            problems.append(FieldProblem(field=field, code='UNSUPPORTED_ASSERTION'))
            continue
        patch[field] = getattr(parsed, field)
    clear = response.get('clear_fields', [])
    if not isinstance(clear, list) or any(field not in LoanRequest.model_fields for field in clear):
        raise InvalidExtraction('Invalid clear_fields')
    accepted_clear = []
    for field in clear:
        try:
            quote = VerbatimEvidence.model_validate({'quote':evidence.get(field)}, context={'text':text}).quote
            if not re.search(r'убер[иь]|очист|удал|сброс|забуд|не\s+зна[юе]|неизвест|не\s+определ|отказываюсь\s+указывать', quote.casefold()):
                raise ValueError('No explicit removal')
            if field in patch:
                raise ValueError('Conflicting change and clear')
            accepted_clear.append(field)
        except (ValidationError, ValueError):
            problems.append(FieldProblem(field=field, code='UNSUPPORTED_ASSERTION'))
    intent = response.get('intent', 'PROVIDE_DETAILS')
    if intent in {'CANCEL','MANUAL_REVIEW'} and not explicit_control_intent(intent,text):
        if patch:
            intent = 'PROVIDE_DETAILS'
        else:
            raise InvalidExtraction('No explicit control intent')
    if intent in {'CANCEL','MANUAL_REVIEW'}:
        VerbatimEvidence.model_validate({'quote':evidence.get('intent')}, context={'text':text})
    # A STATUS label cannot suppress an explicit parameter change.
    if (patch or accepted_clear) and intent == 'STATUS':
        intent = 'PROVIDE_DETAILS'
    for issue in explicit_numeric_problems(text):
        patch.pop(issue.field, None)
        accepted_clear = [field for field in accepted_clear if field != issue.field]
        problems = [old for old in problems if old.field != issue.field] + [issue]
    # Independently inspect the original token: an LLM must not truncate an invalid INN.
    inn_match=re.search(r'\bинн\s*(?:на\s+|[:=—-]\s*)?([0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё_-]*(?:[ \t]+[0-9]+)*)',text,re.IGNORECASE)
    if inn_match:
        token=inn_match.group(1)
        legal_form=patch.get('legal_form',case.request.legal_form)
        lengths=(12,) if legal_form=='IP' else (10,) if legal_form in {'OOO','AO'} else (10,12)
        if not re.fullmatch(r'[0-9]+',token) or len(token) not in lengths:
            patch.pop('inn',None)
            accepted_clear=[field for field in accepted_clear if field!='inn']
            problems=[issue for issue in problems if issue.field!='inn']+[FieldProblem(field='inn',code='INVALID_VALUE')]
        else:
            patch['inn']=token
            evidence['inn']=inn_match.group(0)
            problems=[issue for issue in problems if issue.field!='inn']
    return Extraction(intent=intent, patch=LoanRequest(**patch), clear_fields=accepted_clear,
                      evidence=evidence, ambiguous_subjects=response.get('ambiguous_subjects',[]),
                      multiple_purposes=response.get('multiple_purposes',[]), diagnostics=problems)


def merge_repair(previous: Extraction, current: Extraction) -> Extraction:
    """Keep grounded siblings omitted by repair; never choose between conflicting values."""
    values = current.patch.model_dump(exclude_none=True)
    evidence = current.evidence.copy()
    problems = list(current.diagnostics)
    blocked = {issue.field for issue in problems} | set(current.clear_fields)
    for field,value in previous.patch.model_dump(exclude_none=True).items():
        if field in current.clear_fields:
            problems.append(FieldProblem(field=field,code='CONFLICT'))
            continue
        if field in values and values[field] != value:
            values.pop(field)
            problems.append(FieldProblem(field=field,code='CONFLICT'))
        elif field not in values and field not in blocked:
            values[field] = value
            evidence[field] = previous.evidence[field]
    clear=list(current.clear_fields)
    for field in previous.clear_fields:
        if field in values:
            values.pop(field)
            problems.append(FieldProblem(field=field,code='CONFLICT'))
        elif field not in blocked and field not in clear:
            clear.append(field)
            evidence[field]=previous.evidence[field]
    conflicted={issue.field for issue in problems if issue.code=='CONFLICT'}
    clear=[field for field in clear if field not in conflicted]
    resolved = set(values) | set(clear)
    diagnosed = {issue.field for issue in problems}
    for issue in previous.diagnostics:
        if issue.field not in resolved and issue.field not in diagnosed:
            problems.append(issue)
            diagnosed.add(issue.field)
    return current.model_copy(update={'patch':LoanRequest(**values),'clear_fields':clear,'evidence':evidence,'diagnostics':problems})
