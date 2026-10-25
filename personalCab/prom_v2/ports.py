"""Explicit replaceable boundaries; absent business modules never emulate a decision."""
from typing import Protocol

from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import Extraction
from personalCab.prom.prom_lab.ai_agents_lab.schemas.products import ProductSelection
from personalCab.prom.rag.models import KnowledgeAnswer

from .models import Actor, Case, Command


class Extractor(Protocol):
    def extract(self, text: str, case: Case) -> Extraction: ...


class Knowledge(Protocol):
    def is_question(self, text: str) -> bool: ...
    def ask(self, text: str, case: Case) -> KnowledgeAnswer: ...


class Products(Protocol):
    def select(self, case: Case) -> ProductSelection: ...


class BusinessModules(Protocol):
    """Future idempotent M3–M5 adapter, with case/revision and trusted actor checks.

    Results must match the subject and revision. The adapter owns operation receipts
    and external-effect recovery; a local DB rollback cannot roll back a bank call.
    """

    def supports(self, action: str) -> bool: ...
    def execute(self, actor: Actor, case: Case, command: Command) -> dict: ...


class UnavailableModules:
    def supports(self, action: str) -> bool:
        return False

    def execute(self, actor: Actor, case: Case, command: Command) -> dict:
        raise RuntimeError("Business modules are not configured for V2")
