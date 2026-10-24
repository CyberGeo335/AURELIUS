"""Three offline functional scenarios: retrieval, source lifecycle, dialogue safety."""
import hashlib
import json

from personalCab.prom.rag import RequirementsRAG, is_requirements_question
from personalCab.prom.rag.index import KNOWLEDGE_PATH, load_index
from personalCab.frontend.server import result_envelope
from ..agents.workflow import WorkflowApp
from ..schemas.models import Extraction
from .test_workflow import ScriptedExtractor, actor, full, msg


def test_faiss_grounding_and_product_legal_form_scope():
    index = load_index()
    assert index.index.ntotal == 99
    for code in ('R01', 'R02', 'R03'):
        term = next(row for row in index.source.products[code].requirements if row.field_code == f'{code}_06')
        assert term.target_db_field == 'credit_applications.requested_term_months'
    rag = RequirementsRAG()
    answer = rag.ask('Какой формат ИНН для R01 ООО?')
    assert answer.status == 'FOUND' and answer.citations[0].field_code == 'R01_03'
    assert answer.source_sha256 == hashlib.sha256(KNOWLEDGE_PATH.read_bytes()).hexdigest()
    assert all(hit.product_code == 'R01' for hit in answer.citations)
    for hit in answer.citations:
        offset = int(hit.source_ref.rsplit('/', 1)[1])
        original = index.source.products[hit.product_code].requirements[offset]
        assert hit.format_rule == original.format_rule and hit.field_code == original.field_code
        assert hit.source_ref in answer.answer
    checklist = rag.ask('Какие требования к заявке R02 для ИП?')
    expected = {r.field_code for r in index.source.products['R02'].requirements if r.required_ip}
    assert {hit.field_code for hit in checklist.citations} == expected
    assert 'R02_10' in expected and 'R02_11' not in expected
    natural = rag.ask('Какие обязательные поля для оформления заявки на кредитную линию для ИП?')
    assert {hit.field_code for hit in natural.citations} == expected
    kpp = rag.ask('Нужен ли КПП для заявки R01 ИП?')
    assert kpp.citations[0].field_code == 'R01_11'
    assert 'для ИП не отмечено обязательным' in kpp.answer
    assert rag.ask('Какой срок транша для R02 ООО?').citations[0].field_code == 'R02_32'
    assert rag.ask('Какой порог одобрения заявки R01?').status == 'NOT_FOUND'
    assert rag.ask('Какие документы нужны для заявки R04 ООО?').status == 'NOT_FOUND'
    assert rag.ask('Какие документы нужны для заявки?').status == 'CLARIFY_PRODUCT'
    assert rag.ask('Какие поля заявки R01 для АО?').status == 'UNSUPPORTED_LEGAL_FORM'


def test_source_changes_reindex_and_invalid_source_fails_closed(tmp_path):
    path = tmp_path / 'requirements.json'
    path.write_bytes(KNOWLEDGE_PATH.read_bytes())
    rag = RequirementsRAG(path)
    first = rag.ask('Объясни поле R01_03')
    data = json.loads(path.read_text())
    data['products']['R01']['requirements'][2]['format_rule'] = 'Тестовая новая версия источника'
    path.write_text(json.dumps(data, ensure_ascii=False))
    second = rag.ask('Объясни поле R01_03')
    assert first.source_sha256 != second.source_sha256
    assert second.citations[0].format_rule == 'Тестовая новая версия источника'
    data['total_requirements'] = 1
    path.write_text(json.dumps(data))
    assert rag.ask('Объясни поле R01_03').status == 'UNAVAILABLE'
    path.write_text('{broken')
    assert rag.ask('Объясни поле R01_03').status == 'UNAVAILABLE'
    path.unlink()
    assert rag.ask('Объясни поле R01_03').status == 'UNAVAILABLE'


def test_langgraph_chat_grounding_replay_and_no_application_mutation(tmp_path):
    for text in ('Нужен кредит R01 на 3000000 рублей', 'Какой статус заявки?', 'Измени сумму заявки на 5000000',
                 'Я ИП. ИНН 1234567890123. Нужно 3000000 рублей на товар на 24 месяца.',
                 'ИНН 123456789012, нужно 1000000 рублей'):
        assert not is_requirements_question(text)
    extractor = ScriptedExtractor(full(), Extraction(intent='CANCEL', evidence={'intent': 'Отмени'}))
    database = tmp_path / 'cases.db'
    question = msg('knowledge', 'Какой формат ИНН для R01 ООО?')
    with WorkflowApp(database, extractor=extractor) as app:
        initial = app.handle(msg(), actor())
        result = app.handle(question, actor())
        assert result.next_action == 'KNOWLEDGE_ANSWER' and extractor.calls == 1
        assert result.knowledge_answer.citations[0].field_code == 'R01_03'
        assert result.request == initial.request and result.revision == initial.revision
        assert result.status == initial.status and result.result_refs == initial.result_refs
        assert result.request.legal_form == 'IP'  # ООО in reference question is not a client fact.
        wire = json.loads(json.dumps(result_envelope(result)))
        assert wire['workflow_log']['knowledge_answer']['citations'][0]['field_code'] == 'R01_03'
        assert not any(t.tool_name in ('update_request', 'request_evidence', 'run_assessment', 'submit_application') for t in result.tool_traces)
        replay = app.handle(question, actor())
        assert replay == result and extractor.calls == 1
        cancelled = app.handle(msg('cancel', 'Отмени обращение'), actor())
        assert cancelled.status.value == 'CANCELLED'
        after = app.handle(msg('after-cancel', 'Какие поля нужны для заявки R03 ИП?'), actor())
        assert after.status == cancelled.status and after.knowledge_answer.status == 'FOUND'
    with WorkflowApp(database, extractor=ScriptedExtractor()) as app:
        assert app.handle(question, actor()) == result
