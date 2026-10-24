from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class KnowledgeModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Requirement(KnowledgeModel):
    product_code: str
    field_number: int = Field(gt=0)
    field_code: str
    field_label: str
    required_ip: StrictBool
    required_ooo: StrictBool
    format_rule: str
    source_description: str
    fill_method: str
    target_db_field: str


class ProductRequirements(KnowledgeModel):
    name: str
    requirements: list[Requirement]


class KnowledgeSource(KnowledgeModel):
    total_requirements: int
    products: dict[str, ProductRequirements]

    @model_validator(mode='after')
    def consistent_inventory(self):
        rows = [r for p in self.products.values() for r in p.requirements]
        if len(rows) != self.total_requirements or len({r.field_code for r in rows}) != len(rows):
            raise ValueError('Requirement count or unique identifiers do not match')
        for code, product in self.products.items():
            if any(r.product_code != code or r.field_code != f'{code}_{r.field_number:02d}' for r in product.requirements):
                raise ValueError('Inconsistent product/field identifier')
        return self


class Citation(KnowledgeModel):
    field_code: str
    product_code: str
    label: str
    format_rule: str
    source_description: str
    fill_method: str
    target_db_field: str
    required_ip: bool
    required_ooo: bool
    source_ref: str
    score: float


class KnowledgeAnswer(KnowledgeModel):
    status: Literal['FOUND', 'NOT_FOUND', 'UNAVAILABLE', 'CLARIFY_PRODUCT', 'UNSUPPORTED_LEGAL_FORM']
    query: str
    answer: str = ''
    source_sha256: str | None = None
    retrieval: Literal['FAISS_TFIDF_WORD_CHAR_V1'] = 'FAISS_TFIDF_WORD_CHAR_V1'
    product_codes: list[str] = Field(default_factory=list)
    legal_form: str | None = None
    citations: list[Citation] = Field(default_factory=list)
