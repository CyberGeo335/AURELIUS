from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from personalCab.prom.rag import RequirementsRAG, is_requirements_question

from .factory import Extractor, OllamaExtractor
from ..agent_tools.tools import ToolBox
from ..schemas.resolution import FieldProblem
from ..services.data_resolution import build_resolution
from ..services.extraction_validation import explicit_numeric_problems
from ..repositories.case_repository import CaseRepository
from ..repositories.postgres_case_repository import create_case_repository, PostgresCaseRepository
from ..schemas.models import ActorContext, Case, DialogueResult, Extraction, FIELD_LABELS, MessageInput, Status, ToolTrace, explicit_control_intent, utcnow
from ..services.workflow_service import ModuleAdapter, TERMINAL, ToolSession, UnconfiguredModules, grounded_patch, transition


class DialogueState(TypedDict, total=False):
    knowledge_answer: dict | None
    message: dict
    actor: dict
    case: dict
    extraction: dict | None
    traces: list[dict]
    error_code: str | None
    next_action: str
    next_module: int | None
    result: dict


class DialogueWorkflow:
    def __init__(self, repository: CaseRepository, extractor: Extractor, adapter: ModuleAdapter, checkpointer):
        self.repository, self.extractor, self.adapter = repository, extractor, adapter
        self.requirements_rag = RequirementsRAG()
        graph = StateGraph(DialogueState)
        graph.add_node("load_case", self.load_case)
        graph.add_node("retrieve_requirements", self.retrieve_requirements)
        graph.add_node("extract_intent", self.extract_intent)
        graph.add_node("advance_workflow", self.advance_workflow)
        graph.add_node("respond", self.respond)
        graph.add_node("persist", self.persist)
        graph.add_edge(START, "load_case")
        graph.add_edge("load_case", "retrieve_requirements")
        graph.add_edge("retrieve_requirements", "extract_intent")
        graph.add_edge("extract_intent", "advance_workflow")
        graph.add_edge("advance_workflow", "respond")
        graph.add_edge("respond", "persist")
        graph.add_edge("persist", END)
        self.graph = graph.compile(checkpointer=checkpointer, name="aurelius_dialogue_workflow")

    def box(self, state: DialogueState, case: Case) -> ToolBox:
        return ToolBox(ToolSession(case, ActorContext.model_validate(state["actor"]), self.repository, self.adapter))

    def load_case(self, state: DialogueState) -> dict:
        case = Case.model_validate(state["case"])
        box = self.box(state, case)
        box.invoke("load_case")
        box.invoke("find_existing_application")
        return {"traces": [trace.model_dump(mode="json") for trace in box.traces]}

    def extract_intent(self, state: DialogueState) -> dict:
        case = Case.model_validate(state["case"])
        if state.get('knowledge_answer') or case.status in TERMINAL or state['message'].get('command','CHAT') != 'CHAT':
            return {"extraction": Extraction(intent="STATUS").model_dump(mode="json")}
        try:
            extraction = Extraction.model_validate(self.extractor.extract(MessageInput.model_validate(state["message"]), case))
            return {"extraction": extraction.model_dump(mode="json")}
        except Exception:
            return {"extraction": None, "error_code": "LLM_UNAVAILABLE_OR_INVALID_OUTPUT"}

    def retrieve_requirements(self, state: DialogueState) -> dict:
        message = MessageInput.model_validate(state['message'])
        if message.command != 'CHAT' or not is_requirements_question(message.text):
            return {'knowledge_answer': None}
        case = Case.model_validate(state['case'])
        codes = []
        if case.product_selection:
            codes = [candidate.database_product_code or candidate.product_id
                     for candidate in case.product_selection.candidates if candidate.eligibility != 'NO_MATCH']
        answer = self.requirements_rag.ask(message.text, codes, case.request.legal_form)
        return {'knowledge_answer': answer.model_dump(mode='json')}

    def advance_workflow(self, state: DialogueState) -> dict:
        if state.get('knowledge_answer'):
            return {'next_action': 'KNOWLEDGE_ANSWER', 'next_module': None}
        case = Case.model_validate(state["case"])
        actor = ActorContext.model_validate(state["actor"])
        message = MessageInput.model_validate(state["message"])
        box = self.box(state, case)
        case.profile_lookup_status = "NOT_NEEDED"
        for issue in explicit_numeric_problems(message.text):
            case.pending_clarifications = [old for old in case.pending_clarifications if old.field != issue.field] + [issue]
        action, next_module, error = "ASK_FIELDS", None, state.get("error_code")

        def invoke(operation: str, **kwargs):
            nonlocal error, action, next_module
            result = box.invoke(operation, **kwargs)
            if not result.ok:
                error = case.last_error = result.code
                if result.code == "CONSENT_REQUIRED":
                    transition(case, Status.WAITING_CONSENT)
                    case.pending_action = operation
                    action = "PROVIDE_CONSENT"
                elif result.code == "UNSUPPORTED_DATABASE_ROUTE":
                    transition(case, Status.NEEDS_INPUT)
                    action, next_module = "DATABASE_ROUTE_UNSUPPORTED", None
                elif result.code == "CONSENT_DENIED":
                    transition(case, Status.NEEDS_INPUT)
                    case.pending_action = operation
                    action = "ALTERNATIVE_ROUTE"
                elif result.code=='STALE_PROCESS':
                    action,next_module='RESOLVE_STALE_PROCESS',None
                elif result.code=='UNRESOLVED_CLARIFICATIONS':
                    transition(case,Status.NEEDS_INPUT)
                    action,next_module='ASK_FIELDS',None
                else:
                    action = "CONNECT_MODULE" if result.code == "MODULE_NOT_CONFIGURED" else "RETRY_TOOL"
            return result

        def lookup_missing_profile():
            if case.request.legal_form is not None:
                return
            if not hasattr(self.adapter, "supports") or not self.adapter.supports("lookup_business_profile"):
                case.profile_lookup_status = "UNSUPPORTED"
                return
            response = box.invoke("lookup_business_profile")
            if not response.ok:
                case.profile_lookup_status = "CONSENT_REQUIRED" if response.code in {"CONSENT_REQUIRED", "CONSENT_DENIED"} else "UNAVAILABLE"

        def route():
            nonlocal action, next_module, error
            if case.status in TERMINAL:
                action = "DONE"
                return
            if message.command=='POLL_STATUS' and message.arguments:
                raise ValueError('Status polling accepts no arguments')
            if message.command == 'UPDATE_REQUEST':
                if set(message.arguments) - {'patch','clear_fields'}:
                    raise ValueError('Unknown request update arguments')
                if not invoke('update_request',**message.arguments).ok:
                    return
                corrected = {field for field,value in message.arguments.get('patch',{}).items() if value is not None} | set(message.arguments.get('clear_fields',[]))
                case.pending_clarifications = [issue for issue in case.pending_clarifications if issue.field not in corrected]
            elif message.command == 'REFRESH_EVIDENCE':
                if message.arguments:
                    raise ValueError('Refresh accepts no arguments')
                if 'bank_application' in case.result_refs:
                    case.revision += 1
                case.data_cutoff_at = utcnow()
                case.result_refs = {}
                case.data_context = case.evidence_recheck = case.assessment = case.bank_application = None
                case.product_selection = case.product_requirements = None
                case.verified_facts = []
                case.pending_action = None
                transition(case,Status.REQUEST_READY if not case.missing_required else Status.NEEDS_INPUT)
            elif message.command in {'ASSESS','SUBMIT','ACCEPT_OFFER','EXECUTE_DEMO'}:
                if not case.data_context or 'evidence' not in case.result_refs:
                    action, error = 'REVIEW_DATA_QUALITY','EVIDENCE_REQUIRED'
                    return
                operation = {'ASSESS':'run_assessment','SUBMIT':'submit_application','ACCEPT_OFFER':'accept_offer','EXECUTE_DEMO':'execute_demo'}[message.command]
                response = invoke(operation,**message.arguments)
                if not response.ok:
                    return
                case.pending_action = None
                if message.command == 'ASSESS':
                    if case.status==Status.WAITING_CONSENT:
                        transition(case,Status.WAITING_DOCUMENTS)
                    elif case.status==Status.NEEDS_INPUT:
                        transition(case,Status.REQUEST_READY)
                        transition(case,Status.WAITING_DOCUMENTS)
                    action, next_module = 'ASSESSMENT_READY', 5
                elif message.command == 'SUBMIT':
                    transition(case,Status.WAITING_EXTERNAL)
                    action,next_module = 'POLL_EXISTING_PROCESS',5
                elif message.command == 'ACCEPT_OFFER':
                    if case.status in {Status.WAITING_CONSENT,Status.NEEDS_INPUT,Status.MANUAL_REVIEW}:
                        transition(case,Status.WAITING_EXTERNAL)
                    action,next_module = 'OFFER_ACCEPTED',5
                else:
                    if response.data.get('status') == 'EXECUTED_DEMO' and response.data.get('execution',{}).get('confirmed') is True and response.data['execution'].get('simulated') is True:
                        if case.status in {Status.WAITING_CONSENT,Status.NEEDS_INPUT,Status.MANUAL_REVIEW}:
                            transition(case,Status.WAITING_EXTERNAL)
                        transition(case,Status.COMPLETED)
                        action,next_module = 'DONE',None
                    else:
                        action,error = 'RETRY_TOOL','EXECUTION_UNCONFIRMED'
                return
            if error:
                lookup_missing_profile()
                action = "ASK_FIELDS" if case.missing_required or case.pending_clarifications else "RETRY_MESSAGE"
                if action == "ASK_FIELDS" or case.status == Status.DISCOVERY:
                    transition(case, Status.NEEDS_INPUT)
                return
            extraction = Extraction.model_validate(state["extraction"])
            if extraction.ambiguous_subjects or len(extraction.multiple_purposes) > 1:
                transition(case, Status.NEEDS_INPUT)
                action = "SELECT_BORROWER" if extraction.ambiguous_subjects else "SPLIT_PURPOSES"
                return
            if extraction.intent in {"CANCEL", "MANUAL_REVIEW"}:
                quote = " ".join(extraction.evidence.get("intent", "").casefold().split())
                if quote and quote in " ".join(message.text.casefold().split()) and explicit_control_intent(extraction.intent, message.text):
                    transition(case, Status.CANCELLED if extraction.intent == "CANCEL" else Status.MANUAL_REVIEW)
                    action = "DONE" if case.status == Status.CANCELLED else "HUMAN_HANDOFF_REQUIRED"
                    return
                error, action = "UNGROUNDED_INTENT", "RETRY_MESSAGE"
                return
            if extraction.intent != "STATUS":
                patch, clear, rejected = grounded_patch(extraction, message.text)
                if patch or clear:
                    if not invoke("update_request", patch=patch, clear_fields=clear).ok:
                        return
                corrected = set(patch) | set(clear)
                case.pending_clarifications = [issue for issue in case.pending_clarifications if issue.field not in corrected]
                new_issues = [*extraction.diagnostics, *[FieldProblem(field=field, code="UNGROUNDED_QUOTE") for field in rejected]]
                for issue in new_issues:
                    case.pending_clarifications = [old for old in case.pending_clarifications if old.field != issue.field] + [issue]
                if rejected:
                    error = "UNGROUNDED_FIELDS"
            if "legal_form" not in extraction.clear_fields:
                lookup_missing_profile()
            if case.pending_clarifications:
                transition(case, Status.NEEDS_INPUT)
                action, next_module = "ASK_FIELDS", None
                return
            for ref in message.document_refs:
                if ref not in case.document_refs:
                    case.document_refs.append(ref)
            if case.missing_required:
                transition(case, Status.NEEDS_INPUT)
                action = "ASK_FIELDS"
                return
            if case.status == Status.MANUAL_REVIEW:
                if 'bank_application' in case.result_refs:
                    transition(case,Status.WAITING_EXTERNAL)
                else:
                    action = "HUMAN_HANDOFF_REQUIRED"
                    return
            if case.pending_action in {"get_assessment_status", "get_bank_status"} and case.status in {Status.WAITING_CONSENT, Status.NEEDS_INPUT}:
                transition(case, Status.WAITING_EXTERNAL)
            if case.status == Status.WAITING_EXTERNAL:
                operation = "get_bank_status" if "bank_application" in case.result_refs else "get_assessment_status"
                next_module = 5 if operation == "get_bank_status" else 4
                if ("bank_application" if next_module == 5 else "assessment") not in case.result_refs:
                    action = "WAIT_FOR_INTEGRATION"
                    return
                response = invoke(operation)
                if not response.ok:
                    return
                if response.data.get("status") == "MANUAL_REVIEW":
                    action = "POLL_EXISTING_PROCESS"
                elif response.data.get('status') in {'OFFERED','ACCEPTED','DECLINED','REQUEST_DATA','EXECUTED_DEMO'}:
                    action = {'OFFERED':'CHOOSE_DEMO_OFFER','ACCEPTED':'OFFER_ACCEPTED','DECLINED':'DEMO_DECLINED',
                              'REQUEST_DATA':'PROVIDE_DOCUMENTS','EXECUTED_DEMO':'DONE'}[response.data['status']]
                    if response.data['status']=='DECLINED':
                        transition(case,Status.COMPLETED)
                    if response.data['status']=='EXECUTED_DEMO' and response.data.get('execution',{}).get('confirmed') is True and response.data['execution'].get('simulated') is True:
                        transition(case,Status.COMPLETED)
                elif next_module == 5 and response.data.get("status") == "COMPLETED" and response.data.get("confirmed") is True:
                    transition(case, Status.COMPLETED)
                    action = "DONE"
                elif next_module == 4 and response.data.get("status") == "READY":
                    action, next_module = "HANDOFF_MODULE_5", 5
                else:
                    action = "POLL_EXISTING_PROCESS"
                return
            # Existing requests to module 3 are not recreated for every chat turn.
            if hasattr(self.adapter, "needs_refresh") and self.adapter.needs_refresh(case):
                case.result_refs = {key: value for key, value in case.result_refs.items() if key == "bank_application"}
                case.product_selection = None
                case.product_requirements = None
                case.data_context = None
            if "evidence" in case.result_refs:
                transition(case, Status.WAITING_DOCUMENTS)
                if case.data_context:
                    action, next_module = "REVIEW_DATA_QUALITY", None
                    return
                action, next_module = "PROVIDE_DOCUMENTS", 3
                return
            transition(case, Status.REQUEST_READY)
            next_module = 2
            if case.product_selection and case.product_selection.status == "NEEDS_CLARIFICATION":
                transition(case, Status.NEEDS_INPUT)
                action, next_module = "CLARIFY_PRODUCT_NEED", None
                return
            for operation, key in (("get_product_candidates", "products"), ("get_data_requirements", "requirements")):
                if key not in case.result_refs:
                    response = invoke(operation)
                    if not response.ok:
                        return
                    case.result_refs[key] = response.result_ref
                    if key == "products" and case.product_selection and case.product_selection.status == "NEEDS_CLARIFICATION":
                        transition(case, Status.NEEDS_INPUT)
                        action, next_module = "CLARIFY_PRODUCT_NEED", None
                        return
            next_module = 3
            transition(case, Status.WAITING_DOCUMENTS)
            response = invoke("request_evidence")
            if response.ok:
                case.result_refs["evidence"] = response.result_ref
                case.pending_action = None
                action = "PROVIDE_DOCUMENTS"
                if case.data_context:
                    # Recheck module 2 on the facts of the same immutable cutoff.
                    transition(case, Status.REQUEST_READY)
                    for operation, key in (("get_product_candidates", "products"), ("get_data_requirements", "requirements")):
                        updated = invoke(operation)
                        if not updated.ok:
                            return
                        case.result_refs[key] = updated.result_ref
                        if key == "products" and case.product_selection.status == "NEEDS_CLARIFICATION":
                            transition(case, Status.NEEDS_INPUT)
                            action, next_module = "CLARIFY_PRODUCT_NEED", None
                            return
                    transition(case, Status.WAITING_DOCUMENTS)
                    case.evidence_recheck = {
                        'evidence_ref':case.result_refs['evidence'],
                        'snapshot_product_selection_ref':case.data_context['product_selection_ref'],
                        'snapshot_requirements_ref':case.data_context['requirements_ref'],
                        'current_product_selection_ref':case.result_refs['products'],
                        'current_requirements_ref':case.result_refs['requirements'],
                        'revision':case.revision,'decision_at':case.data_cutoff_at.isoformat(),
                        'status':'RECHECKED',
                    }
                    action, next_module = "REVIEW_DATA_QUALITY", None

        route()
        if not error:
            case.last_error = None
        return {"case": case.model_dump(mode="json"), "next_action": action, "next_module": next_module,
                "error_code": error, "traces": state["traces"] + [trace.model_dump(mode="json") for trace in box.traces]}

    def respond(self, state: DialogueState) -> dict:
        case = Case.model_validate(state["case"])
        action, error = state["next_action"], state.get("error_code")
        case.data_resolution = build_resolution(case)
        if action == 'KNOWLEDGE_ANSWER':
            message = state['knowledge_answer']['answer']
        elif action == "ASK_FIELDS":
            questions = [gap.question for gap in case.data_resolution.gaps if gap.question][:3]
            prefix = "Корректные сведения сохранены. " if case.pending_clarifications else ""
            message = prefix + "Чтобы подготовить запрос, уточните: " + " ".join(questions)
            if case.profile_lookup_status == "CONSENT_REQUIRED":
                message += " Для проверки профиля в БД нужно отдельное согласие; форму можно сообщить здесь."
            elif case.profile_lookup_status == "UNAVAILABLE":
                message += " Проверка профиля в БД сейчас недоступна; данные не подставлялись."
        elif action == "SELECT_BORROWER":
            message = "Выберите одно ИП или компанию для этого обращения. Данные разных субъектов не объединяются."
        elif action == "CLARIFY_PRODUCT_NEED":
            message = case.product_selection.clarification
        elif action == "DATABASE_ROUTE_UNSUPPORTED":
            message = "Продуктовый маршрут сохранён, но сбор данных PostgreSQL подключён только для R01–R03. Для выбранного направления нужен отдельный адаптер; автоматическая замена продукта не выполнялась."
        elif action == "REVIEW_DATA_QUALITY":
            message = "Снимок данных сохранён. Проверьте адресные уточнения в анкете; после исправлений обновите данные. Оценка доступна по явным проверенным входам модели, недостающие значения не подставляются."
        elif action == 'ASSESSMENT_READY':
            message = 'Модуль 4 завершил проверку: ' + (case.assessment or {}).get('status','UNKNOWN') + '. Результат и причины сохранены. Решение принимает оператор DEMO; заявку можно передать на ручное рассмотрение.'
        elif action=='RESOLVE_STALE_PROCESS':
            message='Данные, оценка или предложение изменились. Повторите оценку; для нового рассмотрения при необходимости обновите данные и создайте новую ревизию. Устаревшее предложение не исполнялось.'
        elif action == 'CHOOSE_DEMO_OFFER':
            message = 'Оператор предоставил предложение DEMO. Проверьте сумму, ставку, комиссии, срок и график. Принятие предложения и запуск симуляции требуют отдельных подтверждений в интерфейсе.'
        elif action == 'OFFER_ACCEPTED':
            message = 'Предложение DEMO принято. Это не юридическая подпись. Для симуляции исполнения используйте отдельную кнопку подтверждения.'
        elif action == 'DEMO_DECLINED':
            message = 'Оператор завершил рассмотрение DEMO с отказом. Причины сохранены в карточке; это не решение реального банка.'
        elif action == "SPLIT_PURPOSES":
            message = "В сообщении несколько потребностей. Уточните одну цель и относящиеся к ней сумму и срок; остальные оформим отдельно."
        elif action == "PROVIDE_CONSENT":
            if case.pending_action == 'request_evidence':
                message = 'Заявка сохранена. Чтобы заполнить анкету сведениями о вашем бизнесе, откройте «Согласия и данные бизнеса» над перепиской. Отметьте «Разрешаю получить сведения о моём бизнесе», затем нажмите «Обновить данные и анкету». Пока разрешение не дано, сведения не загружаются.'
            else:
                message = 'Параметры заявки сохранены. Для следующего шага нужно отдельное разрешение. Откройте «Согласия и данные бизнеса» над перепиской, отметьте согласие для нужного действия и повторите это действие. Само согласие не означает одобрение кредита.'
        elif action == "ALTERNATIVE_ROUTE":
            message = "Доступ к источнику не предоставлен. Зависимые запросы остановлены; требуется уточнить альтернативный способ предоставления данных."
        elif action == "PROVIDE_DOCUMENTS":
            message = "Запрос документов создан подключённым модулем сбора данных. Ссылки из сообщений сохраняются как непроверенные; результаты проверки ожидаются."
        elif action == "HUMAN_HANDOFF_REQUIRED":
            message = "Кейс помечен для ручного рассмотрения. Фактическую передачу специалисту должен подтвердить подключённый процесс."
        elif action == "HANDOFF_MODULE_5":
            message = "Подключённый модуль подтвердил готовность оценки. Следующий шаг — передача модулю решения; одобрение кредита ещё не получено."
        elif case.status == Status.CANCELLED:
            message = "Обращение отменено. Для новой потребности начните новую сессию."
        elif case.status == Status.COMPLETED:
            message = "Демонстрационный процесс завершён по подтверждённому результату адаптера. Реальная выдача кредита не выполнялась."
        elif action in {"POLL_EXISTING_PROCESS", "WAIT_FOR_INTEGRATION"}:
            message = "Ожидается результат существующего внешнего процесса. Новый процесс не создавался."
        elif error == "MODULE_NOT_CONFIGURED":
            if case.product_selection:
                names = [candidate.name for candidate in case.product_selection.candidates if candidate.eligibility != "NO_MATCH"]
                message = "Предварительные кандидаты: " + ", ".join(names) + f". Ограничения и необходимые документы — в общем логе. Следующий шаг — модуль {state['next_module']}, он пока не подключён. Подбор не является одобрением кредита."
            else:
                message = f"Запрос сохранён. Для следующего шага требуется подключить модуль {state['next_module']}. Кредитное решение не принималось."
        elif action == "RETRY_MESSAGE":
            message = "Не удалось надёжно разобрать сообщение. Уточните сведения или повторите запрос; недостающие значения не заполнены предположениями."
        else:
            message = "Запрос сохранён, но инструмент не выполнил следующий шаг. Можно повторить после восстановления сервиса. Это не кредитный отказ."
        if error == "COMPANY_BINDING_REQUIRED":
            message = "Для модуля 3 нужна выбранная оператором тестовая компания PostgreSQL (--company-id). Идентификатор из текста чата не предоставляет доступа."
        result = DialogueResult(case_id=case.case_id, revision=case.revision, mode=case.mode, status=case.status,
                                correlation_id=case.correlation_id, request=case.request, unknown_fields=case.unknown_fields,
                                next_module=state.get("next_module"), next_action=action, message=message,
                                result_refs=case.result_refs, tool_traces=[ToolTrace.model_validate(t) for t in state["traces"]], error_code=error,
                                product_selection=case.product_selection, product_requirements=case.product_requirements, data_context=case.data_context, data_resolution=case.data_resolution)
        result.evidence_recheck = case.evidence_recheck
        result.assessment = case.assessment
        result.bank_application = case.bank_application
        result.knowledge_answer = state.get('knowledge_answer')
        result.client_changes = case.client_changes
        return {"result": result.model_dump(mode="json")}

    def persist(self, state: DialogueState) -> dict:
        case = Case.model_validate(state["case"])
        message = MessageInput.model_validate(state["message"])
        result = DialogueResult.model_validate(state["result"])
        case.history = (case.history + [{"role": "user", "content": message.text}, {"role": "assistant", "content": result.message}])[-16:]
        self.repository.commit(case, case.storage_version, message, result)
        return {"case": case.model_dump(mode="json")}


class WorkflowApp:
    """Local single-host DEMO runtime. Identity is supplied by its caller."""

    def __init__(self, database=None, *, extractor: Extractor | None = None, adapter: ModuleAdapter | None = None):
        self.repository = create_case_repository(database)
        if isinstance(self.repository, PostgresCaseRepository):
            from langgraph.checkpoint.postgres import PostgresSaver
            self.checkpoint_connection = self.repository.config.connect(workflow=True, autocommit=True)
            self.checkpointer = PostgresSaver(self.checkpoint_connection)
        else:
            self.checkpoint_connection = sqlite3.connect(self.repository.path, check_same_thread=False, timeout=15)
            self.checkpointer = SqliteSaver(self.checkpoint_connection)
        if adapter is None:
            if isinstance(self.repository, PostgresCaseRepository):
                from ..services.database_modules import DatabaseModules
                adapter = DatabaseModules(self.repository.config)
            else:
                from ..services.product_matching import ProductModuleAdapter
                adapter = ProductModuleAdapter()
        self.workflow = DialogueWorkflow(self.repository, extractor or OllamaExtractor(), adapter, self.checkpointer)

    def handle(self, message: MessageInput, actor: ActorContext) -> DialogueResult:
        with self.repository.actor_lock(actor.actor_id):
            case = self.repository.open_session(message, actor)
            receipt = self.repository.receipt(message, actor)
            if receipt:
                return receipt
            case.correlation_id = uuid4().hex
            # A checkpoint thread represents one idempotent command. The domain case
            # persists across commands; chat checkpoint history is not its database.
            thread_id = hashlib.sha256(f"{actor.actor_id}:{message.session_id}:{message.message_id}".encode()).hexdigest()
            initial: DialogueState = {"message": message.model_dump(mode="json"), "actor": actor.model_dump(mode="json"),
                                      "case": case.model_dump(mode="json"), "traces": [], "error_code": None,
                                      "extraction": None, "next_action": "", "next_module": None, "result": {}}
            try:
                final = self.workflow.graph.invoke(initial, {"configurable": {"thread_id": thread_id}, "recursion_limit": 12})
            except Exception:
                receipt = self.repository.receipt(message, actor)
                if receipt:  # Commit succeeded but a final checkpoint write failed.
                    return receipt
                raise
            return DialogueResult.model_validate(final["result"])

    def close(self):
        self.checkpoint_connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
