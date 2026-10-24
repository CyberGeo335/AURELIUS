"""Extractive RAG subgraph. Retrieved source text is data, never instructions."""
from __future__ import annotations

from pathlib import Path
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .index import KNOWLEDGE_PATH, load_index, words
from .models import KnowledgeAnswer


class RAGState(TypedDict, total=False):
    query: str
    product_codes: list[str]
    legal_form: str | None
    result: dict


def is_requirements_question(text: str) -> bool:
    normalized = text.lower().replace('ё', 'е')
    question = bool(re.search(r'\b(каки[ехм]|како[йег]|какая|сколько|расскажи|покажи|перечисли|объясни|зачем|откуда|чем)\w*', normalized)) or '?' in text
    question = question or bool(re.search(r'\b(нужен|нужны|нужна|нужно|требуется|требуются)\s+(?:ли\s+)?(?:документ|требован|пол[еяю]\b|инн|кпп|огрн)', normalized))
    topic = bool(re.search(r'требован|документ|анкет|заявк|пол[еяю]|формат|инн|кпп|огрн|транш|период.*выбор|r\d{2}', normalized))
    # Explicit mutation/control requests always stay in the ordinary workflow.
    mutation = re.search(r'\b(измени|поменяй|установи|отмени|отменить|оставь|новая|новую|создай|подай|подтверждаю)\b', normalized)
    status_question = re.search(r'\b(статус|этап|готовность)\b', normalized) and not re.search(r'требован|формат|пол[еяю]\b|документ', normalized)
    return bool(question and topic and not mutation and not status_question)


def query_scope(query: str, product_codes: list[str], legal_form: str | None):
    upper = query.upper()
    explicit = sorted(set(re.findall(r'\bR\d{2}\b|\bR\d{2}(?=_\d{2}\b)', upper)))
    names = []
    if 'ОВЕРДРАФТ' in upper:
        names.append('R03')
    if 'КРЕДИТН' in upper and 'ЛИНИ' in upper:
        names.append('R02')
    if 'РАЗОВ' in upper:
        names.append('R01')
    codes = explicit or names or product_codes
    forms = re.findall(r'\b(ИП|ООО|АО)\b', upper)
    form = {'ИП': 'IP', 'ООО': 'OOO', 'АО': 'AO'}.get(forms[0]) if len(set(forms)) == 1 else None if forms else legal_form
    return list(dict.fromkeys(codes)), form


class RequirementsRAG:
    def __init__(self, source_path: Path = KNOWLEDGE_PATH):
        self.source_path = source_path
        graph = StateGraph(RAGState)
        graph.add_node('resolve_scope', self.resolve_scope)
        graph.add_node('retrieve_faiss', self.retrieve)
        graph.add_node('compose_grounded_answer', self.compose)
        graph.add_edge(START, 'resolve_scope')
        graph.add_edge('resolve_scope', 'retrieve_faiss')
        graph.add_edge('retrieve_faiss', 'compose_grounded_answer')
        graph.add_edge('compose_grounded_answer', END)
        self.graph = graph.compile(name='application_requirements_rag')

    def resolve_scope(self, state: RAGState):
        codes, form = query_scope(state['query'], state.get('product_codes', []), state.get('legal_form'))
        return {'product_codes': codes, 'legal_form': form}

    def retrieve(self, state: RAGState):
        answer = KnowledgeAnswer(status='NOT_FOUND', query=state['query'], product_codes=state['product_codes'], legal_form=state.get('legal_form'))
        try:
            index = load_index(self.source_path)
            answer.source_sha256 = index.sha256
            if not state['product_codes']:
                answer.status = 'CLARIFY_PRODUCT'
            elif state.get('legal_form') not in (None, 'IP', 'OOO'):
                answer.status = 'UNSUPPORTED_LEGAL_FORM'
            else:
                # Broad checklist is a complete structured view, still filtered by scope.
                broad = not words(state['query'])
                answer.citations = index.search(state['query'], state['product_codes'], state.get('legal_form'), enumerate_all=broad)
                answer.status = 'FOUND' if answer.citations else 'NOT_FOUND'
        except (OSError, ValueError, TypeError):
            answer.status = 'UNAVAILABLE'
        return {'result': answer.model_dump(mode='json')}

    def compose(self, state: RAGState):
        result = KnowledgeAnswer.model_validate(state['result'])
        if result.status == 'FOUND':
            lines = ['По справочнику требований к кредитным заявкам:']
            for hit in result.citations:
                applicable = 'ИП и ООО' if hit.required_ip and hit.required_ooo else 'ИП' if hit.required_ip else 'ООО' if hit.required_ooo else 'не отмечено обязательным'
                if result.legal_form == 'IP' and not hit.required_ip:
                    applicable += '; для ИП не отмечено обязательным'
                elif result.legal_form == 'OOO' and not hit.required_ooo:
                    applicable += '; для ООО не отмечено обязательным'
                # Plain excerpts: frontend uses textContent; never render source as HTML.
                lines.append(f'[{hit.field_code}] {hit.label}. Формат: {hit.format_rule}. Источник данных: {hit.source_description}. Заполнение: {hit.fill_method}. Обязательно для: {applicable}. Источник требования: {hit.source_ref}')
            lines.append('Это требования к заполнению анкеты; они не подтверждают данные клиента, согласие или одобрение кредита.')
            result.answer = '\n'.join(lines)
        elif result.status == 'CLARIFY_PRODUCT':
            result.answer = 'Уточните продукт: R01 — разовый кредит, R02 — возобновляемая линия, R03 — овердрафт. Требования справочника зависят от продукта и формы ИП/ООО.'
        elif result.status == 'UNAVAILABLE':
            result.answer = 'Справочник требований сейчас недоступен или не прошёл проверку структуры. Повторите вопрос после восстановления источника.'
        elif result.status == 'UNSUPPORTED_LEGAL_FORM':
            result.answer = 'В справочнике указаны требования только для ИП и ООО. Применимость к выбранной форме не установлена.'
        else:
            result.answer = 'В справочнике не найдено подтверждённого ответа для указанного продукта и формы. Уточните название поля или код требования; условий и финансовых правил из предположений не добавляю.'
        return {'result': result.model_dump(mode='json')}

    def ask(self, query: str, product_codes: list[str] | None = None, legal_form: str | None = None) -> KnowledgeAnswer:
        final = self.graph.invoke({'query': query[:4000], 'product_codes': product_codes or [], 'legal_form': legal_form})
        return KnowledgeAnswer.model_validate(final['result'])
