"""Read-only compatibility adapters for reviewed V1 primitives, not its workflow."""
from copy import deepcopy
import json
import os

from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import Case as ExtractionContext, LoanRequest
from personalCab.prom.prom_lab.ai_agents_lab.services.extraction_validation import validate_extraction, merge_repair, InvalidExtraction
from personalCab.prom.prom_lab.ai_agents_lab.services.product_matching import ProductMatcher, load_catalog
from personalCab.prom.rag.pipeline import RequirementsRAG, is_requirements_question

from .models import Case

PRODUCT_CODES = {"term": "R01", "rcl": "R02", "overdraft": "R03"}


def extraction_context(case: Case) -> ExtractionContext:
    return ExtractionContext(
        case_id=case.case_id, owner_id=case.owner_id, company_id=case.company_id,
        revision=case.revision, request=case.request.model_copy(deep=True),
        history=deepcopy(case.history), pending_clarifications=deepcopy(case.problems),
    )


def checked_extraction(raw, text, case):
    from .declared_facts import declared_facts
    raw = declared_facts(raw, text)
    context = extraction_context(case)
    # V1 skips validation of unchanged values. A proposal must be grounded even
    # when the model repeats a known value contradicted by the new message.
    context.request = context.request.model_copy(update={
        field: None for field, value in raw.get("patch", {}).items()
        if field in LoanRequest.model_fields and field != "borrower_id" and value is not None
    })
    return validate_extraction(raw, text, context)


class OllamaExtraction:
    def __init__(self, base_url: str | None = None):
        from langchain_ollama import ChatOllama
        from personalCab.prom.prom_lab.ai_agents_lab.agents.factory import SYSTEM_PROMPT, extraction_schema
        self.prompt = SYSTEM_PROMPT + "\nV2: результат — только предложение изменений; подтверждение выполняет отдельная типизированная команда."
        model = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "gpt-oss:20b"), base_url=base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0, num_ctx=16384, num_predict=4096, reasoning="low", client_kwargs={"timeout": 120},
        )
        self.chain = model.with_structured_output(extraction_schema(), method="json_schema")

    def extract(self, text: str, case: Case):
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from zoneinfo import ZoneInfo
        from .models import utcnow
        context = {"current_request": case.request.model_dump(mode="json"),
                   "today_moscow": utcnow().astimezone(ZoneInfo("Europe/Moscow")).date().isoformat(),
                   "history": [{**item, "content": item["content"][:1000]} for item in case.history[-8:]], "current_message": text}
        messages = [SystemMessage(content=self.prompt), HumanMessage(content=json.dumps(context, ensure_ascii=False))]
        partial = None
        for attempt in range(2):
            response = None
            try:
                response = self.chain.invoke(messages)
                result = checked_extraction(response, text, case)
                result = merge_repair(partial, result) if partial is not None else result
                if not result.diagnostics:
                    return result
                partial = result
            except Exception:
                if partial is not None:
                    return partial
            if attempt:
                if partial is not None:
                    return partial
                raise InvalidExtraction("No grounded extraction after one repair")
            messages.extend([
                AIMessage(content=json.dumps(response, ensure_ascii=False)),
                HumanMessage(content="Исправь структуру JSON и точные цитаты текущего сообщения. Сохрани корректные поля; неизвестное оставь null."),
            ])
        raise AssertionError("Unreachable")


class ReferenceKnowledge:
    def __init__(self):
        self.rag = RequirementsRAG()

    def is_question(self, text: str) -> bool:
        return is_requirements_question(text)

    def ask(self, text: str, case: Case):
        code = PRODUCT_CODES.get(case.selected_product_id)
        return self.rag.ask(text, [code] if code else [], case.request.legal_form)


class CatalogProducts:
    def __init__(self):
        catalog = load_catalog().model_copy(deep=True)
        for card in catalog.products:
            card.database_product_code = PRODUCT_CODES.get(card.product_id)
            card.database_supported = card.product_id in PRODUCT_CODES
            if not card.database_supported:
                card.limitations.append("V2: бизнес-адаптер этого направления отсутствует; R01 не подставляется.")
        self.matcher = ProductMatcher(catalog)

    def select(self, case: Case):
        return self.matcher.select(
            case.case_id, case.revision, case.request, [], now=case.data_cutoff_at,
        )
