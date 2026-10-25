"""Independent V2 LangGraph orchestrator: route, execute, project; commit atomically."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import FIELD_LABELS, REQUIRED_FIELDS
from personalCab.prom.prom_lab.ai_agents_lab.schemas.resolution import DataGap, DataResolutionPlan, FieldProblem
from personalCab.prom.prom_lab.ai_agents_lab.services.questionnaire import validate_answer

from .adapters import CatalogProducts, ReferenceKnowledge, checked_extraction
from .models import Action, Actor, Case, Command, LoanRequest, Proposal, Scope, View, utcnow
from .ports import UnavailableModules
from .repository import AccessDenied, Conflict


BUSINESS_SCOPES = {
    Action.REFRESH_EVIDENCE: Scope.EVIDENCE_COLLECTION,
    Action.ASSESS: Scope.CREDIT_ASSESSMENT,
    Action.SUBMIT: Scope.APPLICATION_SUBMISSION,
    Action.POLL_STATUS: Scope.BANK_STATUS,
    Action.ACCEPT_OFFER: Scope.APPLICATION_SUBMISSION,
    Action.EXECUTE_DEMO: Scope.DEMO_EXECUTION,
}
EDITABLE_FIELDS = set(LoanRequest.model_fields) - {"borrower_id"}
TERMINAL = {"CANCELLED", "DECLINED", "EXECUTED_DEMO"}


class Turn(TypedDict, total=False):
    actor: Actor
    command: Command
    case: Case
    route: str
    message: str
    error: str | None
    knowledge: dict | None
    view: View


class Agent:
    def __init__(self, repository, *, extractor=None, knowledge=None, products=None, modules=None):
        self.repository = repository
        self.extractor = extractor
        self.knowledge = knowledge if knowledge is not None else ReferenceKnowledge()
        self.products = products if products is not None else CatalogProducts()
        self.modules = modules if modules is not None else UnavailableModules()
        graph = StateGraph(Turn)
        graph.add_node("route", self._route)
        graph.add_node("execute", self._execute)
        graph.add_node("project", self._project_turn)
        graph.add_edge(START, "route")
        graph.add_edge("route", "execute")
        graph.add_edge("execute", "project")
        graph.add_edge("project", END)
        # PostgreSQL case + receipt is the source of state. No V1 graph checkpoints.
        self.graph = graph.compile(name="aurelius_agent_v2")

    def handle(self, actor: Actor, command: Command) -> View:
        if actor.role != "BORROWER":
            raise AccessDenied("BORROWER_COMMAND_REQUIRED")

        def apply(case):
            final = self.graph.invoke({"actor": actor, "command": command, "case": case})
            return final["view"]

        return self.repository.transact(actor, command, apply)

    def state(self, actor: Actor, case_id: str) -> View:
        case = self.repository.get(actor, case_id)
        return self._view(actor, case, self._question(case))

    def cases(self, actor: Actor) -> list[dict]:
        return [{"case_id": case.case_id, "version": case.version, "revision": case.revision,
                 "status": case.status, "request": case.request.model_dump(mode="json"),
                 "selected_product_id": case.selected_product_id}
                for case in self.repository.list(actor)]

    def capabilities(self) -> dict[str, bool]:
        return {
            "knowledge": True, "extraction_configured": self.extractor is not None,
            "durable_storage": self.repository.durable,
            **{action.value.lower(): self.modules.supports(action.value) for action in BUSINESS_SCOPES},
        }

    def _route(self, turn: Turn):
        command = turn["command"]
        reference = command.action == Action.CHAT and self.knowledge.is_question(command.text)
        return {"route": "reference" if reference else "dialogue" if command.action == Action.CHAT else "command"}

    def _execute(self, turn: Turn):
        case, command, actor = turn["case"], turn["command"], turn["actor"]
        message, error, knowledge = "", None, None
        if turn["route"] == "reference":
            answer = self.knowledge.ask(command.text, case.model_copy(deep=True))
            message, knowledge = answer.answer, answer.model_dump(mode="json")
            case.last_knowledge_answer = answer
        elif case.status in TERMINAL:
            if command.action==Action.CHAT and re.search(r'статус|решени|исполн|почему',command.text.casefold()) and not re.search(r'измени|поменяй|отмени|создай',command.text.casefold()):
                message=self._question(case)
            else:
                message, error = "Обращение закрыто. Создайте новое обращение.", "CASE_CLOSED"
        elif command.action == Action.CHAT:
            message, error = self._chat(case, command)
        elif command.action == Action.CREATE:
            message = "Обращение создано. Расскажите о задаче или заполните форму."
        elif command.action == Action.LOOKUP_PROFILE:
            self._arguments(command, set())
            denial = self.action_denial(actor, case, command.action)
            if denial:
                message, error = denial[1], denial[0]
            else:
                from personalCab.prom.prom_lab.ai_agents_lab.schemas.resolution import BusinessProfileResult
                case.data_cutoff_at = utcnow() if not case.data_context else case.data_cutoff_at
                try:
                    raw_profile=self.modules.lookup_profile(case.model_copy(deep=True))
                except Exception:
                    case.profile_lookup_status='UNAVAILABLE'
                    case.history.append({'role':'assistant','content':'Проверенный источник временно недоступен. Укажите форму бизнеса или повторите чтение профиля.'})
                    case.version+=1
                    return {'case':case,'message':case.history[-1]['content'],'error':'PROFILE_UNAVAILABLE','knowledge':None}
                profile = BusinessProfileResult.model_validate(raw_profile)
                if (profile.company_id, profile.borrower_id, profile.decision_at) != (case.company_id, case.borrower_id, case.data_cutoff_at):
                    raise ValueError('Profile scope mismatch')
                case.business_profile = profile.model_dump(mode='json')
                facts = [f for f in profile.verified_facts if f.field == 'legal_form']
                case.profile_lookup_status='CONFLICT' if profile.conflicts else 'FOUND' if facts else 'NOT_FOUND'
                if not profile.conflicts and len(facts) == 1 and case.request.legal_form is None:
                    self._update(case, {'legal_form': facts[0].value}, [], 'VERIFIED_PROFILE')
                    # _update advances the revision/cutoff; preserve exact point-in-time provenance.
                    case.data_cutoff_at = profile.decision_at
                    self._select_products(case)
                message = ('Источник содержит конфликт формы бизнеса; требуется проверка сотрудника.' if profile.conflicts else
                           'Проверенная форма бизнеса получена; источник и время сохранены.' if facts else
                           'Проверенная форма бизнеса не найдена. Укажите её в анкете.')
                if facts and case.request.legal_form != facts[0].value:
                    message = 'Форма бизнеса в запросе отличается от проверенного источника. Проверьте конфликт в досье.'
        elif command.action == Action.UPDATE_REQUEST:
            if case.status in {"ACCEPTED"}:
                raise Conflict("ACCEPTED_CASE_CANNOT_BE_EDITED")
            self._arguments(command, {"patch", "clear_fields"})
            patch = command.arguments.get("patch", {})
            clear = command.arguments.get("clear_fields", [])
            if not isinstance(patch, dict) or not isinstance(clear, list) or any(not isinstance(field, str) for field in clear):
                raise ValueError("Expected patch object and clear_fields list")
            self._update(case, patch, clear, "FORM")
            case.pending = None
            message = self._question(case)
        elif command.action == Action.CONFIRM_FACTS:
            if case.status == "ACCEPTED":
                raise Conflict("ACCEPTED_CASE_CANNOT_BE_EDITED")
            self._arguments(command, {"proposal_id"}, required={"proposal_id"})
            if case.pending is None or command.arguments["proposal_id"] != case.pending.proposal_id:
                raise Conflict("STALE_PROPOSAL")
            self._update(case, case.pending.patch, case.pending.clear_fields, "CHAT_CONFIRMED")
            case.pending = None
            message = self._question(case)
        elif command.action == Action.SELECT_PRODUCT:
            if case.status == "ACCEPTED":
                raise Conflict("ACCEPTED_CASE_CANNOT_BE_EDITED")
            self._arguments(command, {"product_id"}, required={"product_id"})
            if not isinstance(command.arguments["product_id"], str):
                raise ValueError("product_id must be a catalog identifier")
            self._select_products(case)
            candidate = next((item for item in case.product_selection.candidates
                              if item.product_id == command.arguments["product_id"]), None)
            if candidate is None or candidate.eligibility == "NO_MATCH":
                raise ValueError("Product is not an available candidate")
            if case.selected_product_id != candidate.product_id:
                self._invalidate(case)
                case.selected_product_id = candidate.product_id
                self._select_products(case)
            message = "Продукт выбран. Подбор не является одобрением кредита."
            if not candidate.database_supported:
                error = "DATABASE_ROUTE_UNSUPPORTED"
                message = "Направление сохранено. Для него нет бизнес-адаптера; обычный кредит не подставляется."
        elif command.action == Action.CANCEL:
            self._arguments(command, set())
            if case.status == "ACCEPTED":
                raise Conflict("ACCEPTED_CASE_REQUIRES_OPERATOR_REVIEW")
            self._invalidate(case)
            case.status, case.pending = "CANCELLED", None
            message = "Обращение отменено; история сохранена."
        elif command.action in BUSINESS_SCOPES:
            message, error = self._business(actor, case, command)
        else:
            raise ValueError("Unsupported V2 action")
        if command.action == Action.CHAT:
            case.history.append({"role": "user", "content": command.text})
        case.history.append({"role": "assistant", "content": message})
        case.version += 1
        return {"case": case, "message": message, "error": error, "knowledge": knowledge}

    @staticmethod
    def _arguments(command, allowed, required=frozenset()):
        if set(command.arguments) - allowed or required - set(command.arguments):
            raise ValueError("Invalid command arguments")

    def _chat(self, case: Case, command: Command):
        if self.extractor is None:
            return "Извлечение через модель не настроено. Можно заполнить форму или спросить требования к полям.", "EXTRACTION_UNAVAILABLE"
        try:
            raw = self.extractor.extract(command.text, case.model_copy(deep=True))
            result = checked_extraction(raw.model_dump(mode="json"), command.text, case)
            for problem in raw.diagnostics:
                if problem not in result.diagnostics:
                    result.diagnostics.append(problem)
        except Exception:
            # No user content, secrets or model response in error text/logs.
            return "Не удалось надёжно извлечь сведения. Уточните сообщение или воспользуйтесь формой.", "EXTRACTION_INVALID"
        patch = result.patch.model_dump(mode="json", exclude_none=True)
        patch.pop("borrower_id", None)
        clears = [name for name in result.clear_fields if name in EDITABLE_FIELDS]
        self._merge_problems(case, result.diagnostics, resolved=set())
        if result.ambiguous_subjects or result.multiple_purposes:
            case.pending = None
            return "Уточните одну потребность выбранной компании. Полномочия и компанию задаёт серверный вход.", "AMBIGUOUS_REQUEST"
        if patch or clears:
            case.pending = Proposal(
                patch=patch, clear_fields=clears, quotes={key: value for key, value in result.evidence.items() if key in set(patch) | set(clears)},
                source_message_id=command.request_id, source_text=command.text,
            )
            return "Проверьте извлечённые сведения. В заявку они попадут после явного подтверждения.", None
        case.pending = None
        if result.intent == "CANCEL":
            return "Для отмены используйте отдельное действие «Отменить обращение».", None
        if result.intent == "MANUAL_REVIEW":
            return "Ручное рассмотрение выполняет уполномоченный сотрудник; сообщение не создаёт решение.", None
        return self._question(case), None

    @staticmethod
    def _merge_problems(case, incoming, resolved):
        by_field = {problem.field: problem for problem in case.problems if problem.field not in resolved}
        by_field.update({problem.field: problem for problem in incoming})
        case.problems = list(by_field.values())

    def _update(self, case, patch, clear, source):
        if set(patch) - EDITABLE_FIELDS or set(clear) - EDITABLE_FIELDS or set(patch) & set(clear):
            raise ValueError("Unknown, identity or conflicting request fields")
        accepted, problems = {}, []
        for field, value in patch.items():
            try:
                # JSON validation preserves typed dates; strict rejects numeric strings/bools.
                parsed = LoanRequest.model_validate_json(json.dumps({field: value}), strict=True)
                if value is None:
                    raise ValueError("Use clear_fields to remove a value")
                if field == "inn":
                    legal_form = patch.get("legal_form", case.request.legal_form)
                    if legal_form not in {"IP", "OOO", "AO", "OTHER"}:
                        legal_form = case.request.legal_form
                    validate_answer(value, "text", "companies.inn", legal_form)
                accepted[field] = getattr(parsed, field)
            except (ValidationError, ValueError, TypeError):
                problems.append(FieldProblem(field=field, code="INVALID_VALUE"))
        updates = {**accepted, **{field: None for field in clear}}
        changed = {key: value for key, value in updates.items() if getattr(case.request, key) != value}
        if changed:
            before = case.request.model_dump(mode="json")
            new_request = LoanRequest.model_validate({**case.request.model_dump(), **updates})
            self._invalidate(case)
            case.request = new_request
            after = case.request.model_dump(mode="json")
            case.client_changes.extend({"field": field, "old_value": before[field], "new_value": after[field],
                                        "revision": case.revision, "source": source, "verification": "UNVERIFIED"}
                                       for field in changed)
        self._merge_problems(case, problems, resolved=set(accepted) | set(clear))
        if problems:
            case.status = "NEEDS_INFO"
        if case.request.inn is not None:
            try:
                validate_answer(case.request.inn, "text", "companies.inn", case.request.legal_form)
            except ValueError:
                self._merge_problems(case, [FieldProblem(field="inn", code="CONFLICT")], resolved=set())
            else:
                case.problems = [p for p in case.problems if not (p.field == 'inn' and p.code == 'CONFLICT')]
        if case.status == 'NEEDS_INFO' and not case.problems and not case.bank_application and not any(r.status == 'OPEN' for r in case.follow_ups):
            case.status = 'DRAFT'
        self._select_products(case)

    @staticmethod
    def _invalidate(case, *, preserve_follow_ups=False):
        previous_offer=(case.bank_application or {}).get('offer')
        if previous_offer and not any(h['offer']['offer_id']==previous_offer['offer_id'] for h in case.offer_history):
            case.offer_history.append({'offer':previous_offer,'revision':case.revision,
                                       'reviewed_by':'legacy','invalidated_at':None})
        for offer in case.offer_history:
            if offer.get('invalidated_at') is None:
                offer['invalidated_at'] = utcnow().isoformat()
        case.revision += 1
        case.data_cutoff_at = utcnow()
        case.data_context = case.assessment = case.bank_application = None
        case.evidence_stale = False
        case.checking_error = None
        case.product_selection = None
        case.pending = None
        case.status = "DRAFT"
        if not preserve_follow_ups:
            for request in case.follow_ups:
                if request.status=='OPEN':request.status='SUPERSEDED'

    def evidence_changed(self, case: Case) -> None:
        """Keep the historical snapshot visible, but revoke its downstream use."""
        previous_snapshot = case.data_context
        self._invalidate(case, preserve_follow_ups=True)
        case.data_context = previous_snapshot
        case.evidence_stale = True
        case.status = "NEEDS_INFO"
        self._select_products(case)

    def _select_products(self, case):
        case.product_selection = self.products.select(case)
        if case.selected_product_id and not any(
            item.product_id == case.selected_product_id and item.eligibility != "NO_MATCH"
            for item in case.product_selection.candidates
        ):
            case.selected_product_id = None

    @staticmethod
    def _question(case):
        if case.status == "CANCELLED":
            return "Обращение отменено."
        if case.checking_error:
            return "Ответ сохранён. Повторная проверка ждёт обновления данных: " + case.checking_error
        if any(r.status == 'OPEN' for r in case.follow_ups):
            return "Сотрудник запросил сведения. Ответьте на перечисленные поля и документы дозапроса."
        if case.status=='CHECKING' and not case.evidence_stale:
            return "Ответ принят, данные обновлены. Запустите повторную оценку, затем передайте заявку на рассмотрение." if not case.assessment else "Повторная оценка получена. Передайте заявку на рассмотрение сотруднику."
        if case.evidence_stale:
            return "Новые сведения сохранены. Обновите снимок данных и повторите оценку и рассмотрение; прежнее предложение больше не действует."
        if case.bank_application:
            lender=case.bank_application
            labels={'MANUAL_REVIEW':'Заявка на ручном рассмотрении у сотрудника.', 'REQUEST_DATA':'Сотрудник запросил дополнительные сведения.',
                    'OFFERED':'Сотрудник подготовил предложение DEMO. Проверьте условия перед принятием.',
                    'ACCEPTED':'Предложение принято. Исполнение требует отдельного подтверждения DEMO.',
                    'DECLINED':'Сотрудник сохранил отказ.', 'EXECUTED_DEMO':'Симуляция исполнения подтверждена.'}
            return labels.get(lender['status'],'Статус рассмотрения: '+lender['status'])+' '+ '; '.join(lender.get('review_reasons',[]))
        if case.problems:
            return "Уточните значение: " + FIELD_LABELS.get(case.problems[0].field, {'financing_need':'разовая закупка, регулярные закупки или другая потребность','recurring':'характер повторяемости закупок'}.get(case.problems[0].field,case.problems[0].field)) + "."
        missing = [field for field in REQUIRED_FIELDS if getattr(case.request, field) is None]
        if missing:
            return FIELD_LABELS.get(missing[0], missing[0]).capitalize() + "."
        if not case.selected_product_id:
            return "Запрос подготовлен. Выберите продукт-кандидат; это не одобрение кредита."
        return "Запрос и продукт сохранены. Следующий шаг определяется доступностью данных и разрешений."

    def action_denial(self, actor, case, action):
        """One policy for server execution and every projected list of actions."""
        if actor.role != 'BORROWER': return 'BORROWER_REQUIRED', 'Действие доступно клиенту.'
        if action == Action.CHAT: return None
        if case.status in TERMINAL: return 'CASE_CLOSED', 'Заявка закрыта.'
        if action == Action.LOOKUP_PROFILE:
            if case.status == 'ACCEPTED': return 'CASE_CLOSED', 'Предложение уже принято.'
            if not self.modules.supports(action.value): return 'SERVICE_NOT_CONFIGURED', 'Проверенный профиль не подключён.'
            if not actor.permits(Scope.EVIDENCE_COLLECTION, utcnow()): return 'CONSENT_REQUIRED', 'Для чтения профиля требуется разрешение на получение данных.'
            return None
        if action in {Action.UPDATE_REQUEST,Action.SELECT_PRODUCT,Action.CANCEL,Action.CONFIRM_FACTS}:
            if case.status == 'ACCEPTED': return 'INVALID_LENDING_STAGE', 'Предложение уже принято.'
            if action == Action.CONFIRM_FACTS and not case.pending: return 'STALE_PROPOSAL', 'Нет сведений для подтверждения.'
            if action == Action.SELECT_PRODUCT and not (case.product_selection and case.product_selection.candidates):
                return 'REQUEST_NOT_READY', 'Сначала заполните параметры запроса.'
            return None
        if not self.modules.supports(action.value): return 'SERVICE_NOT_CONFIGURED', 'Сервис этого этапа ещё не подключён к V2.'
        if not actor.permits(BUSINESS_SCOPES[action], utcnow()): return 'CONSENT_REQUIRED', 'Требуется действующее разрешение на это действие.'
        if case.evidence_stale and action != Action.REFRESH_EVIDENCE: return 'EVIDENCE_STALE', 'Сначала обновите снимок данных.'
        if case.status == 'ACCEPTED' and action not in {Action.EXECUTE_DEMO,Action.POLL_STATUS} and not case.evidence_stale:
            return 'INVALID_LENDING_STAGE', 'Предложение принято; доступно подтверждение исполнения.'
        if case.pending or case.problems or any(getattr(case.request, f) is None for f in REQUIRED_FIELDS):
            return 'REQUEST_NOT_READY', 'Сначала подтвердите и уточните сведения запроса.'
        if not case.selected_product_id: return 'PRODUCT_REQUIRED', 'Выберите продукт-кандидат.'
        if not case.product_selection or not any(c.product_id == case.selected_product_id and c.database_supported for c in case.product_selection.candidates):
            return 'DATABASE_ROUTE_UNSUPPORTED', 'Бизнес-адаптер этого направления отсутствует.'
        if action in {Action.ASSESS,Action.SUBMIT}:
            if any(r.status == 'OPEN' for r in case.follow_ups): return 'FOLLOW_UP_OPEN', 'Сначала ответьте на дозапрос.'
            if case.bank_application: return 'INVALID_LENDING_STAGE', 'Заявка уже передана на рассмотрение.'
            if not case.data_context: return 'EVIDENCE_REQUIRED', 'Сначала получите снимок данных.'
        if action == Action.SUBMIT and not case.assessment: return 'ASSESSMENT_REQUIRED', 'Сначала получите результат оценки; неполный результат допускает ручной маршрут.'
        if action == Action.POLL_STATUS and not case.bank_application: return 'SUBMISSION_REQUIRED', 'Заявка ещё не передана на рассмотрение.'
        if action in {Action.ACCEPT_OFFER,Action.EXECUTE_DEMO}:
            expected = 'OFFERED' if action == Action.ACCEPT_OFFER else 'ACCEPTED'
            offer = (case.bank_application or {}).get('offer')
            if case.status != expected or not offer: return 'INVALID_LENDING_STAGE', 'Нет предложения для этого действия.'
            if datetime.fromisoformat(offer['expires_at']) <= utcnow(): return 'OFFER_EXPIRED', 'Предложение истекло; нужна повторная проверка.'
        return None

    def _business(self, actor, case, command):
        was_checking=case.status=='CHECKING'
        allowed_arguments = {
            Action.REFRESH_EVIDENCE: set(), Action.ASSESS: {"horizon_months"},
            Action.SUBMIT: set(), Action.POLL_STATUS: set(),
            Action.ACCEPT_OFFER: {"offer_id", "acknowledge_demo"},
            Action.EXECUTE_DEMO: {"offer_id", "acknowledge_demo"},
        }
        self._arguments(command, allowed_arguments[command.action])
        denial = self.action_denial(actor, case, command.action)
        if denial:
            return denial[1], denial[0]
        if command.action == Action.REFRESH_EVIDENCE and case.bank_application:
            self._invalidate(case, preserve_follow_ups=True)
            self._select_products(case)
        elif command.action == Action.REFRESH_EVIDENCE:
            case.data_cutoff_at=utcnow()
            case.assessment=None
            self._select_products(case)
            if not case.selected_product_id:
                return 'Условия продукта изменились. Выберите доступный продукт повторно.', 'PRODUCT_REQUIRED'
        if command.action in {Action.ACCEPT_OFFER, Action.EXECUTE_DEMO}:
            if command.arguments.get("acknowledge_demo") is not True or not isinstance(command.arguments.get("offer_id"), str) or not command.arguments["offer_id"]:
                raise ValueError("Explicit DEMO acknowledgement and offer_id required")
            expected = "OFFERED" if command.action == Action.ACCEPT_OFFER else "ACCEPTED"
            if case.status != expected:
                raise Conflict("INVALID_LENDING_STAGE")
        # No bundled M3–M5 implementation: a future adapter must satisfy these checks.
        result = self.modules.execute(actor.model_copy(deep=True), case.model_copy(deep=True), command.model_copy(deep=True))
        if not isinstance(result, dict):
            raise ValueError("Business result must be an object")
        expected_scope = (case.case_id, case.revision, case.company_id, case.borrower_id)
        if tuple(result.get(key) for key in ("case_id", "revision", "company_id", "borrower_id")) != expected_scope:
            raise ValueError("Business result scope mismatch")
        permitted = {"case_id", "revision", "company_id", "borrower_id", "data_context", "assessment", "bank_application", "status", "message"}
        if set(result) - permitted:
            raise ValueError("Unknown business result fields")
        target_fields = {Action.REFRESH_EVIDENCE: "data_context", Action.ASSESS: "assessment"}
        target = target_fields.get(command.action, "bank_application")
        if not isinstance(result.get(target), dict):
            raise ValueError("Action-specific business result required")
        if set(result) & ({"data_context", "assessment", "bank_application"} - {target}):
            raise ValueError("Business module cannot write another stage's output")
        if command.action in {Action.REFRESH_EVIDENCE, Action.ASSESS} and result.get("status", case.status) not in {"DRAFT", "NEEDS_INFO", "CHECKING"}:
            raise ValueError("Data collection/scoring cannot issue a credit decision")
        for field in ("data_context", "assessment", "bank_application"):
            if field in result:
                setattr(case, field, result[field])
        if command.action == Action.REFRESH_EVIDENCE:
            case.evidence_stale = False
            case.checking_error = None
        if "status" in result:
            case.status = result["status"]
        if command.action==Action.REFRESH_EVIDENCE:
            if any(r.status=='OPEN' for r in case.follow_ups):case.status='NEEDS_INFO'
            elif was_checking:case.status='CHECKING'
        return result.get("message", "Состояние обновлено доверенным сервисом."), None

    def _view(self, actor, case, message, error=None, knowledge=None):
        gaps = [DataGap(field=problem.field, status="INVALID" if problem.code == "INVALID_VALUE" else "CONFLICT" if problem.code == "CONFLICT" else "UNGROUNDED",
                        resolution="ASK_USER", question=FIELD_LABELS.get(problem.field, problem.field), reason=problem.code)
                for problem in case.problems]
        gaps.extend(DataGap(field=field, status="MISSING", resolution="ASK_USER",
                            question=FIELD_LABELS.get(field, field), reason="Запрошенное значение не указано")
                    for field in REQUIRED_FIELDS if getattr(case.request, field) is None and field not in {gap.field for gap in gaps})
        profile=case.business_profile or {}
        profile_forms={f['value'] for f in profile.get('verified_facts',[]) if f.get('field')=='legal_form'}
        if profile.get('conflicts') or (profile_forms and case.request.legal_form and case.request.legal_form not in profile_forms):
            gaps.append(DataGap(field='legal_form',status='CONFLICT',resolution='ASK_USER',
                                reason='Форма бизнеса отличается от проверенного источника; требуется сверка с сотрудником.'))
        if not self.modules.supports(Action.REFRESH_EVIDENCE.value):
            gaps.append(DataGap(field="business_adapter", status="UNCONFIGURED", resolution="ENGINEERING", reason="M3–M5 ещё не подключены к V2"))
        denials = {a:self.action_denial(actor,case,a) for a in Action if a != Action.CREATE}
        allowed = [a for a,denial in denials.items() if denial is None]
        return View(
            case_id=case.case_id, version=case.version, revision=case.revision, status=case.status,
            request=case.request, selected_product_id=case.selected_product_id, pending=case.pending,
            product_selection=case.product_selection,
            data_resolution=DataResolutionPlan(gaps=gaps, database_lookup=(case.profile_lookup_status if case.profile_lookup_status!='NOT_NEEDED' else 'CONSENT_REQUIRED' if not actor.permits(Scope.EVIDENCE_COLLECTION,utcnow()) else 'NOT_NEEDED') if self.modules.supports('LOOKUP_PROFILE') else 'UNSUPPORTED',
                                              ready_for_product_matching=not case.problems and not case.pending and not any(getattr(case.request, field) is None for field in REQUIRED_FIELDS),
                                              ready_for_scoring=bool(not case.evidence_stale and case.assessment and case.assessment.get("status")=="DEMO_ESTIMATE")),
            message=message, error_code=error, knowledge_answer=knowledge,
            last_knowledge_answer=case.last_knowledge_answer,
            allowed_actions=allowed, capabilities=self.capabilities(),
            action_reasons={a.value:denial[1] for a,denial in denials.items() if denial},
            follow_ups=case.follow_ups, checking_error=case.checking_error,
            data_context=case.data_context,
            assessment=None if case.evidence_stale else case.assessment,
            bank_application=None if case.evidence_stale else case.bank_application,
            evidence_stale=case.evidence_stale,
            business_profile=case.business_profile, review_owner=case.review_owner,
            authority_evidence=case.authority_evidence, offer_history=case.offer_history,
            created_at=case.created_at,
            history=case.history,
        )

    def _project_turn(self, turn: Turn):
        return {"view": self._view(turn["actor"], turn["case"], turn["message"], turn.get("error"), turn.get("knowledge"))}
