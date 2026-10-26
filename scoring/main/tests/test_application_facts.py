from datetime import date, datetime, timezone

import pytest

from main.application_facts import application_company
from main.schemas import InputError


def resolve(monkeypatch, values, company=None, demo_only=True):
    rows = [dict(field_code=code, field_value=value, value_source='CLIENT',
                 verification_status='UNVERIFIED', source_reference='cabinet',
                 obtained_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
                 target_db_field=target) for code, target, value in values]
    def lookup(connection, query, **params):
        assert params == {'id': 123, 'product': 'R01', 'cutoff': date(2026, 10, 26)}
        assert 'd.confirmed_at' in query and 'v.obtained_at' in query
        return rows
    monkeypatch.setattr('main.application_facts._rows', lookup)
    original = company or dict(company_id=41, registration_date=None, okved_main=None,
                                information_reliability_status='UNVERIFIED')
    before = dict(original)
    result = application_company(None, dict(application_id=123, product_code='R01'),
                                 original, date(2026, 10, 26), demo_only=demo_only)
    assert original == before
    return result


def test_missing_model_inputs_use_reported_application_facts_without_verification(monkeypatch):
    company, sources = resolve(monkeypatch, [
        ('R01_15', 'companies.registration_date', '2024-05-04'),
        ('R01_17', 'companies.okved_main + companies.okved_main_name', '46.90'),
    ])
    assert company['registration_date'] == date(2024, 5, 4) and company['okved_main'] == '46.90'
    assert company['information_reliability_status'] == 'UNVERIFIED'
    assert all(s['application_id'] == 123 and s['company_id'] == 41
               and s['verification_status'] == 'UNVERIFIED' for s in sources.values())


def test_reported_inputs_are_not_enabled_in_production(monkeypatch):
    company, sources = resolve(monkeypatch, [('R01_15', 'companies.registration_date', '2024-05-04')], demo_only=False)
    assert company['registration_date'] is None and not sources


@pytest.mark.parametrize('target,value', [
    ('companies.registration_date', '2999-01-01'),
    ('companies.registration_date', '04/05/2024'),
    ('companies.okved_main', 'торговля'),
])
def test_invalid_facts_block_readiness(monkeypatch, target, value):
    with pytest.raises(InputError):
        resolve(monkeypatch, [('bad', target, value)])


def test_conflict_does_not_replace_company_record(monkeypatch):
    with pytest.raises(InputError, match='conflicts'):
        resolve(monkeypatch, [('R01_15', 'companies.registration_date', '2024-05-04')],
                dict(company_id=41, registration_date=date(2019, 1, 15)))
