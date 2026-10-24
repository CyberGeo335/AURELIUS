import pytest
from ..schemas.models import Case,LoanRequest
from ..services.extraction_validation import validate_extraction
from ..services.questionnaire import validate_answer


@pytest.mark.parametrize('value',['1234567890123','12345abc9012','１２３４５６７８９０１２','123 456789012',123456789012])
def test_bad_inn_is_rejected(value):
    with pytest.raises(ValueError):validate_answer(value,'text','companies.inn','IP')


def test_valid_inn_and_legal_form_length():
    assert validate_answer('123456789012','text','companies.inn','IP')=='123456789012'
    with pytest.raises(ValueError):validate_answer('123456789012','text','companies.inn','OOO')


def test_llm_cannot_repair_inn_by_truncating_and_valid_siblings_survive():
    case=Case(owner_id='test',request=LoanRequest(inn='123456789012',legal_form='IP'))
    text='Измени ИНН на 1234567890123, сумма 5000000 рублей'
    result=validate_extraction({'patch':{'inn':'123456789012','amount_rub':5000000},'evidence':{'inn':text,'amount_rub':text}},text,case)
    assert result.patch.inn is None and result.patch.amount_rub==5000000
    assert any(issue.field=='inn' for issue in result.diagnostics)
    assert case.request.inn=='123456789012'


def test_explicit_valid_inn_is_retained_when_model_omits_it():
    text='Мой ИНН 123456789012'
    result=validate_extraction({'patch':{},'evidence':{}},text,Case(owner_id='test'))
    assert result.patch.inn=='123456789012' and not result.diagnostics


@pytest.mark.parametrize('reported_revision,expected',[(1,'123456789012'),(2,'987654321012')])
def test_chat_and_questionnaire_inn_follow_revision_order(reported_revision,expected):
    from ..services.questionnaire import build_questionnaire
    envelope={'product_routes':[{'product_id':'term'}],'request':{'legal_form':'IP','inn':'123456789012'},
              'client_changes':[{'field':'inn','revision':2}]}
    requirements=[{'product_code':'R01','field_code':'R01_03','field_label':'ИНН','required_ip':True,'required_ooo':True,'target_db_field':'companies.inn'}]
    values={('R01','R01_03'):{'field_value':'987654321012','value_source':'CLIENT','reported_revision':reported_revision}}
    result=build_questionnaire(envelope,{'company':{}},requirements,values)
    assert result[0]['value']==expected and result[0]['review_required']
