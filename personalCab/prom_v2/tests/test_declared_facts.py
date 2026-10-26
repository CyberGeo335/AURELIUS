from datetime import date

import pytest

from personalCab.prom_v2.adapters import checked_extraction
from personalCab.prom_v2.models import Case, LoanRequest


@pytest.fixture
def case():
    return Case(case_id='facts', owner_id='client', company_id=35, borrower_id='company:35',
                request=LoanRequest(borrower_id='company:35', legal_form='OOO'))


@pytest.mark.parametrize('field,label,value', [
    ('inn', 'ИНН', '9900000017'),
    ('company_name', 'полное наименование организации', 'ООО Тестовая компания 36'),
    ('ogrn', 'ОГРН', '1990000000032'),
    ('ogrnip', 'ОГРНИП', '399000000000041'),
    ('legal_address', 'юридический адрес', 'г. Москва, ул. Демонстрационная, д. 1'),
    ('director_name', 'ФИО руководителя', 'Иванов Иван Иванович'),
    ('okved_main', 'основной ОКВЭД', '46.90'),
    ('registration_date', 'дата государственной регистрации', '2024-05-04'),
    ('actual_activity_description', 'фактический вид деятельности', 'Оптовая торговля товарами для бизнеса'),
])
def test_nine_reported_fields_are_grounded_even_if_model_omits_them(case, field, label, value):
    if field == 'ogrnip':
        case.request.legal_form = 'IP'
    text = f'Указываю недостающие сведения: {label} — {value}. Мой ИНН — '
    text += '990000000436.' if field == 'ogrnip' else '9900000017.'
    result = checked_extraction({'patch': {}, 'evidence': {}}, text, case)
    assert result.patch.model_dump(mode='json')[field] == value
    assert result.evidence[field] in text
    assert not result.diagnostics


def test_omitted_basic_fields_and_verbatim_quotes_are_recovered(case):
    text = 'Мне нужен кредит 3000000 рублей на 12 месяцев для разовой закупки товаров. Форма бизнеса — ООО.'
    result = checked_extraction({'patch': {'recurring': False},
                                 'evidence': {'recurring': 'разовая закупка'}}, text, case)
    assert result.patch.amount_rub == 3000000 and result.patch.term_months == 12
    assert result.patch.legal_form == 'OOO' and result.patch.recurring is False
    assert result.patch.financing_need == 'ONE_TIME_PURCHASE'
    assert not result.diagnostics


@pytest.mark.parametrize('field,value,text', [
    ('ogrn', '123', 'ОГРН — 123.'),
    ('ogrn', '1990000000032', 'ОГРН — 19900000000321.'),
    ('okved_main', 'торговля', 'основной ОКВЭД — торговля.'),
    ('registration_date', '2999-01-01', 'дата государственной регистрации — 2999-01-01.'),
    ('company_name', 'Придуманная компания', 'полное наименование организации — Моя компания.'),
])
def test_invalid_or_ungrounded_fact_does_not_lose_valid_sibling(case, field, value, text):
    text += ' Нужен кредит 3000000 рублей.'
    result = checked_extraction({'patch': {field: value}, 'evidence': {field: text}}, text, case)
    assert getattr(result.patch, field) is None
    assert result.patch.amount_rub == 3000000
    assert any(problem.field == field for problem in result.diagnostics)


def test_registration_date_is_preserved_without_inventing_age(case):
    text = 'дата государственной регистрации — 2024-05-04.'
    result = checked_extraction({'patch': {'business_age_months': 29},
                                 'evidence': {'business_age_months': text}}, text, case)
    assert result.patch.registration_date == date(2024, 5, 4)
    assert result.patch.business_age_months is None


def test_tranche_term_never_becomes_contract_term(case):
    result = checked_extraction({'patch': {}}, 'Срок транша на 3 месяца.', case)
    assert result.patch.term_months is None
