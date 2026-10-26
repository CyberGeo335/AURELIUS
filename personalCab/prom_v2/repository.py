"""V2-only persistence. PostgreSQL is the default; memory is explicit demo/test storage."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from .models import Actor, Case, Command, View, Action, LoanRequest


class AccessDenied(Exception):
    """The trusted subject cannot access the requested V2 resource."""


class Conflict(Exception):
    """Receipt content, case version or action stage does not match."""


def authorize(case: Case, actor: Actor):
    if (case.owner_id, case.company_id, case.borrower_id) != (
        actor.actor_id, actor.company_id, actor.borrower_id,
    ):
        raise AccessDenied("CASE_NOT_ACCESSIBLE")


def new_case(actor: Actor, command: Command) -> Case:
    identity = json.dumps([actor.actor_id, actor.company_id, actor.borrower_id, command.request_id])
    return Case(
        case_id="V2-" + uuid5(NAMESPACE_URL, identity).hex,
        owner_id=actor.actor_id, company_id=actor.company_id, borrower_id=actor.borrower_id,
        request=LoanRequest(borrower_id=actor.borrower_id),
    )


def digest(actor: Actor, command: Command) -> str:
    # Identity binding is part of the receipt; grants may legitimately expire on replay.
    identity = [actor.actor_id, actor.company_id, actor.borrower_id, actor.role]
    return sha256(json.dumps([identity, command.model_dump(mode="json")], sort_keys=True).encode()).hexdigest()


def check_version(case: Case, command: Command):
    if case.version != command.expected_version:
        raise Conflict("STALE_CASE_VERSION")


class MemoryRepository:
    durable = False

    def __init__(self):
        self._cases: dict[str, Case] = {}
        self._receipts: dict[tuple[str, str], tuple[str, View]] = {}
        self._lock = RLock()

    def get(self, actor: Actor, case_id: str) -> Case:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise AccessDenied("CASE_NOT_ACCESSIBLE")
            authorize(case, actor)
            return case.model_copy(deep=True)

    def list(self, actor: Actor) -> list[Case]:
        with self._lock:
            return [case.model_copy(deep=True) for case in self._cases.values()
                    if (case.owner_id, case.company_id, case.borrower_id) ==
                    (actor.actor_id, actor.company_id, actor.borrower_id)]

    def transact(self, actor: Actor, command: Command, handler: Callable[[Case], View]) -> View:
        with self._lock:
            key, fingerprint = (actor.actor_id, command.request_id), digest(actor, command)
            if key in self._receipts:
                previous_hash, result = self._receipts[key]
                if previous_hash != fingerprint:
                    raise Conflict("REQUEST_ID_REUSED")
                self.get(actor, result.case_id)
                return result.model_copy(deep=True)
            case = new_case(actor, command) if command.action == Action.CREATE else self.get(actor, command.case_id)
            check_version(case, command)
            result = handler(case)
            self._cases[case.case_id] = case.model_copy(deep=True)
            self._receipts[key] = (fingerprint, result.model_copy(deep=True))
            return result
