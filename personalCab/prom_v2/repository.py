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


class PostgresRepository:
    durable = True

    def __init__(self, config):
        self.config = config

    def initialize(self):
        sql = Path(__file__).with_name("migrations").joinpath("001_agent.sql").read_text()
        with self.config.connect() as db:
            db.execute(sql, prepare=False)
            db.execute(Path(__file__).with_name('migrations').joinpath('004_workspace.sql').read_text(), prepare=False)

    @staticmethod
    def _load(db, actor, case_id):
        row = db.execute(
            "SELECT payload FROM aurelius_agent_v2.cases WHERE case_id=%s AND owner_id=%s AND company_id=%s AND borrower_id=%s",
            (case_id, actor.actor_id, actor.company_id, actor.borrower_id),
        ).fetchone()
        if row is None:
            raise AccessDenied("CASE_NOT_ACCESSIBLE")
        case = Case.model_validate(row["payload"])
        authorize(case, actor)
        return case

    def get(self, actor: Actor, case_id: str) -> Case:
        with self.config.connect() as db:
            return self._load(db, actor, case_id)

    def list(self, actor: Actor) -> list[Case]:
        with self.config.connect() as db:
            rows = db.execute(
                "SELECT payload FROM aurelius_agent_v2.cases WHERE owner_id=%s AND company_id=%s AND borrower_id=%s ORDER BY case_id",
                (actor.actor_id, actor.company_id, actor.borrower_id),
            ).fetchall()
        return [Case.model_validate(row["payload"]) for row in rows]

    def transact(self, actor: Actor, command: Command, handler: Callable[[Case], View]) -> View:
        from psycopg.types.json import Jsonb
        fingerprint = digest(actor, command)
        with self.config.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("agent-v2:" + actor.actor_id,))
            row = db.execute(
                "SELECT input_hash,result FROM aurelius_agent_v2.receipts WHERE owner_id=%s AND request_id=%s",
                (actor.actor_id, command.request_id),
            ).fetchone()
            if row:
                if row["input_hash"] != fingerprint:
                    raise Conflict("REQUEST_ID_REUSED")
                result = View.model_validate(row["result"])
                self._load(db, actor, result.case_id)
                return result
            case = new_case(actor, command) if command.action == Action.CREATE else self._load(db, actor, command.case_id)
            check_version(case, command)
            result = handler(case)
            db.execute(
                "INSERT INTO aurelius_agent_v2.cases(case_id,owner_id,company_id,borrower_id,version,payload) "
                "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(case_id) DO UPDATE SET version=EXCLUDED.version,payload=EXCLUDED.payload",
                (case.case_id, case.owner_id, case.company_id, case.borrower_id, case.version, Jsonb(case.model_dump(mode="json"))),
            )
            db.execute(
                "INSERT INTO aurelius_agent_v2.receipts(owner_id,request_id,input_hash,case_id,result) VALUES(%s,%s,%s,%s,%s)",
                (actor.actor_id, command.request_id, fingerprint, case.case_id, Jsonb(result.model_dump(mode="json"))),
            )
            # Bodies and references are retained in private state/receipt, not duplicated in audit.
            db.execute(
                "INSERT INTO aurelius_agent_v2.audit(case_id,version,revision,actor_id,action) VALUES(%s,%s,%s,%s,%s)",
                (case.case_id, case.version, case.revision, actor.actor_id, command.action.value),
            )
            from .workspace import audit_metadata
            db.execute('UPDATE aurelius_agent_v2.audit SET metadata=%s WHERE case_id=%s AND version=%s',
                       (Jsonb(audit_metadata(case)),case.case_id,case.version))
            return result
