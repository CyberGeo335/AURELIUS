from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from .factory import Extractor, OllamaExtractor
from ..agent_tools.tools import ToolBox
from ..repositories.case_repository import CaseRepository
from ..schemas.models import ActorContext, Case, DialogueResult, Extraction, FIELD_LABELS, MessageInput, Status, ToolTrace, explicit_control_intent
from ..services.workflow_service import ModuleAdapter, TERMINAL, ToolSession, UnconfiguredModules, grounded_patch, transition


class DialogueState(TypedDict, total=False):
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
        graph = StateGraph(DialogueState)
        graph.add_node("load_case", self.load_case)
        graph.add_node("extract_intent", self.extract_intent)
        graph.add_node("advance_workflow", self.advance_workflow)
        graph.add_node("respond", self.respond)
        graph.add_node("persist", self.persist)
        graph.add_edge(START, "load_case")
        graph.add_edge("load_case", "extract_intent")
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
        if case.status in TERMINAL:
            return {"extraction": Extraction(intent="STATUS").model_dump(mode="json")}
        try:
            extraction = Extraction.model_validate(self.extractor.extract(MessageInput.model_validate(state["message"]), case))
            return {"extraction": extraction.model_dump(mode="json")}
        except Exception:
            return {"extraction": None, "error_code": "LLM_UNAVAILABLE_OR_INVALID_OUTPUT"}

    def advance_workflow(self, state: DialogueState) -> dict:
        case = Case.model_validate(state["case"])
        actor = ActorContext.model_validate(state["actor"])
        message = MessageInput.model_validate(state["message"])
        box = self.box(state, case)
        action, next_module, error = "ASK_FIELDS", None, state.get("error_code")

        def invoke(operation: str, **kwargs):
            nonlocal error, action
            result = box.invoke(operation, **kwargs)
            if not result.ok:
                error = case.last_error = result.code
                if result.code == "CONSENT_REQUIRED":
                    transition(case, Status.WAITING_CONSENT)
                    case.pending_action = operation
                    action = "PROVIDE_CONSENT"
                elif result.code == "CONSENT_DENIED":
                    transition(case, Status.NEEDS_INPUT)
                    case.pending_action = operation
                    action = "ALTERNATIVE_ROUTE"
                else:
                    action = "CONNECT_MODULE" if result.code == "MODULE_NOT_CONFIGURED" else "RETRY_TOOL"
            return result

        def route():
            nonlocal action, next_module, error
            if case.status in TERMINAL:
                action = "DONE"
                return
            if error:
                action = "RETRY_MESSAGE"
                if case.status == Status.DISCOVERY:
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
                if rejected:
                    error, action = "UNGROUNDED_FIELDS", "RETRY_MESSAGE"
                    return
            for ref in message.document_refs:
                if ref not in case.document_refs:
                    case.document_refs.append(ref)
            if case.missing_required:
                transition(case, Status.NEEDS_INPUT)
                action = "ASK_FIELDS"
                return
            if case.status == Status.MANUAL_REVIEW:
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
                    transition(case, Status.MANUAL_REVIEW)
                    action = "HUMAN_HANDOFF_REQUIRED"
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
            if "evidence" in case.result_refs:
                transition(case, Status.WAITING_DOCUMENTS)
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

        route()
        if not error:
            case.last_error = None
        return {"case": case.model_dump(mode="json"), "next_action": action, "next_module": next_module,
                "error_code": error, "traces": state["traces"] + [trace.model_dump(mode="json") for trace in box.traces]}

    def respond(self, state: DialogueState) -> dict:
        case = Case.model_validate(state["case"])
        action, error = state["next_action"], state.get("error_code")
        if action == "ASK_FIELDS":
            missing = [FIELD_LABELS[field] for field in case.missing_required[:3]]
            message = "Чтобы подготовить запрос, уточните: " + "; ".join(missing) + "."
        elif action == "SELECT_BORROWER":
            message = "Выберите одно ИП или компанию для этого обращения. Данные разных субъектов не объединяются."
        elif action == "CLARIFY_PRODUCT_NEED":
            message = case.product_selection.clarification
        elif action == "SPLIT_PURPOSES":
            message = "В сообщении несколько потребностей. Уточните одну цель и относящиеся к ней сумму и срок; остальные оформим отдельно."
        elif action == "PROVIDE_CONSENT":
            message = "Для следующего действия нужно действующее согласие выбранного субъекта. Оформите его в доверенном интерфейсе приложения. Зависимый запрос пока не выполнялся."
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
        result = DialogueResult(case_id=case.case_id, revision=case.revision, mode=case.mode, status=case.status,
                                correlation_id=case.correlation_id, request=case.request, unknown_fields=case.unknown_fields,
                                next_module=state.get("next_module"), next_action=action, message=message,
                                result_refs=case.result_refs, tool_traces=[ToolTrace.model_validate(t) for t in state["traces"]], error_code=error,
                                product_selection=case.product_selection, product_requirements=case.product_requirements)
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

    def __init__(self, database: Path, *, extractor: Extractor | None = None, adapter: ModuleAdapter | None = None):
        self.repository = CaseRepository(database)
        self.checkpoint_connection = sqlite3.connect(self.repository.path, check_same_thread=False, timeout=15)
        self.checkpointer = SqliteSaver(self.checkpoint_connection)
        if adapter is None:
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
