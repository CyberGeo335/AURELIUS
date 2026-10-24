"""Small offline FAISS index. No pickle, downloads or client facts in the index."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

import faiss
import numpy as np

from .models import Citation, KnowledgeSource

KNOWLEDGE_PATH = Path(__file__).resolve().parents[3] / 'knowledge' / 'Требования к кредитным заявкам.json'
# Exclude question scaffolding, retain domain terms and exact field identifiers.
STOP = set('а и или в во на по для из от с со к у о об это как какой какая какие какого сколько нужно нужен нужна нужны требуется требуются обязательные обязательный требования требование документы документ поля поле заявка заявки заявке кредит кредита кредиту кредитный кредитным ип ооо r01 r02 r03 пожалуйста расскажи покажи список все заполнить'.split())
STOP.update('формат ли должен должна должны быть перечень перечисли'.split())
STOP.update('полей полям полях получения при'.split())
SCAFFOLD_PREFIXES = ('требован', 'заявк', 'кредитн', 'заполнен', 'оформлен', 'обязательн')
PRODUCT_PREFIXES = ('разов', 'оборотн', 'возобновляем', 'овердрафт', 'линия', 'линии', 'линию')


def words(text: str) -> list[str]:
    return [w for w in re.findall(r'[а-яa-z0-9_]+', text.lower().replace('ё', 'е'))
            if w not in STOP and len(w) > 1 and not w.startswith(SCAFFOLD_PREFIXES + PRODUCT_PREFIXES)]


def features(text: str) -> Counter:
    result = Counter()
    for word in words(text):
        result['w:' + word] += 3
        padded = '^' + word + '$'
        for n in (3, 4, 5):
            for start in range(len(padded) - n + 1):
                result[padded[start:start+n]] += 1
    return result


class RequirementsIndex:
    def __init__(self, content: bytes):
        self.source = KnowledgeSource.model_validate(json.loads(content))
        self.sha256 = hashlib.sha256(content).hexdigest()
        self.rows = []
        self.refs = []
        for code, product in self.source.products.items():
            for offset, row in enumerate(product.requirements):
                self.rows.append(row)
                self.refs.append(f'knowledge/{KNOWLEDGE_PATH.name}#/products/{code}/requirements/{offset}')
        documents = [features(' '.join((r.field_code, r.field_label, r.field_label, r.field_label, r.format_rule, r.source_description, r.fill_method, r.target_db_field))) for r in self.rows]
        vocabulary = sorted({term for doc in documents for term in doc})
        self.vocabulary = {term: i for i, term in enumerate(vocabulary)}
        frequency = Counter(term for doc in documents for term in doc)
        self.idf = np.array([np.log((1 + len(documents))/(1 + frequency[term])) + 1 for term in vocabulary], dtype='float32')
        matrix = np.vstack([self.vector(doc) for doc in documents])
        self.index = faiss.IndexFlatIP(len(vocabulary))
        self.index.add(matrix)

    def vector(self, counts: Counter) -> np.ndarray:
        vector = np.zeros(len(self.vocabulary), dtype='float32')
        for term, count in counts.items():
            if term in self.vocabulary:
                i = self.vocabulary[term]
                vector[i] = (1 + np.log(count)) * self.idf[i]
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def search(self, query: str, product_codes: list[str], legal_form: str | None, *, enumerate_all=False, limit=6) -> list[Citation]:
        vector = self.vector(features(query))
        scores, indices = self.index.search(vector.reshape(1, -1), len(self.rows))
        exact = set(re.findall(r'\bR\d{2}_\d{2}\b', query.upper()))
        # Pure character coincidences alone are insufficient for a domain answer.
        query_words = words(query)
        found = []
        for score, offset in zip(scores[0], indices[0]):
            if offset < 0:
                continue
            row = self.rows[offset]
            if row.product_code not in product_codes:
                continue
            targeted_label = any(word in words(row.field_label) for word in words(query))
            if (legal_form == 'IP' and not row.required_ip or legal_form == 'OOO' and not row.required_ooo) and (enumerate_all or not (targeted_label or row.field_code in exact)):
                continue
            if exact and row.field_code not in exact:
                continue
            doc_words = words(' '.join((row.field_code, row.field_label, row.format_rule, row.source_description, row.target_db_field)))
            overlap = any(a == b or (len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]) for a in query_words for b in doc_words)
            if not enumerate_all and not exact and (score < .10 or not overlap):
                continue
            found.append(Citation(**{k: getattr(row, k) for k in ('field_code', 'product_code', 'format_rule', 'source_description', 'fill_method', 'target_db_field', 'required_ip', 'required_ooo')}, label=row.field_label, source_ref=self.refs[offset], score=round(float(score), 6)))
        if enumerate_all:
            return sorted(found, key=lambda hit: hit.field_code)
        return found[:limit]


@lru_cache(maxsize=2)
def _index_for_content(content: bytes) -> RequirementsIndex:
    return RequirementsIndex(content)


def load_index(path: Path = KNOWLEDGE_PATH) -> RequirementsIndex:
    # Bytes, not mtime: changed content gets a new index and source version.
    return _index_for_content(path.read_bytes())
