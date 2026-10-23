from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
from pathlib import Path
import sqlite3

from ..schemas.models import ActorContext, Case, DialogueResult, MessageInput, Status, utcnow


class AccessDenied(PermissionError):
    pass


class ConflictError(RuntimeError):
    pass


def check_access(case: Case, actor: ActorContext) -> None:
    if actor.actor_id != case.owner_id:
        raise AccessDenied("Кейс принадлежит другому пользователю")
    subject = case.request.borrower_id
    if subject and subject not in actor.allowed_borrower_ids:
        raise AccessDenied("Нет полномочий на выбранный субъект")
    if actor.active_borrower_id and subject and actor.active_borrower_id != subject:
        raise AccessDenied("Для другой компании используйте отдельную сессию")


class CaseRepository:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS credit_cases (
                    case_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, borrower_id TEXT,
                    status TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS credit_sessions (
                    owner_id TEXT, session_id TEXT, case_id TEXT NOT NULL,
                    PRIMARY KEY(owner_id, session_id));
                CREATE TABLE IF NOT EXISTS credit_receipts (
                    owner_id TEXT, session_id TEXT, message_id TEXT, input_hash TEXT NOT NULL,
                    result TEXT NOT NULL, PRIMARY KEY(owner_id, session_id, message_id));
                CREATE TABLE IF NOT EXISTS credit_audit (
                    id INTEGER PRIMARY KEY, case_id TEXT, revision INTEGER,
                    correlation_id TEXT, message_id TEXT, event_at TEXT, payload TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def actor_lock(self, actor_id: str):
        """Cross-process serialization on one DB/owner; released on process exit."""
        folder = self.path.parent / "locks"
        folder.mkdir(exist_ok=True)
        key = hashlib.sha256((str(self.path) + actor_id).encode()).hexdigest()
        with (folder / (key + ".lock")).open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ConflictError("Другое сообщение этого пользователя ещё обрабатывается") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def load(self, case_id: str, actor: ActorContext) -> Case:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM credit_cases WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise KeyError("Кейс не найден")
        case = Case.model_validate_json(row["payload"])
        check_access(case, actor)
        return case

    def find_existing(self, actor: ActorContext, borrower_id: str) -> list[Case]:
        if borrower_id not in actor.allowed_borrower_ids:
            raise AccessDenied("Нет полномочий на субъект")
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM credit_cases WHERE owner_id=? AND borrower_id=? AND status NOT IN (?,?)", (actor.actor_id, borrower_id, Status.CANCELLED, Status.COMPLETED)).fetchall()
        return [Case.model_validate_json(row["payload"]) for row in rows]

    def open_session(self, message: MessageInput, actor: ActorContext) -> Case:
        if actor.role not in ("BORROWER", "OPERATOR"):
            raise AccessDenied("Роль не разрешает управление заявкой")
        if actor.active_borrower_id and actor.active_borrower_id not in actor.allowed_borrower_ids:
            raise AccessDenied("Выбранный субъект отсутствует в полномочиях")
        with self.connect() as db:
            row = db.execute("SELECT case_id FROM credit_sessions WHERE owner_id=? AND session_id=?", (actor.actor_id, message.session_id)).fetchone()
            if row:
                return self.load(row["case_id"], actor)
            existing = self.find_existing(actor, actor.active_borrower_id) if actor.active_borrower_id else []
            if len(existing) > 1:
                raise ConflictError("Найдено несколько заявок: требуется выбор существующего кейса")
            case = existing[0] if existing else Case(owner_id=actor.actor_id)
            if not existing:
                case.request.borrower_id = actor.active_borrower_id
                db.execute("INSERT INTO credit_cases VALUES(?,?,?,?,?,?)", (case.case_id, case.owner_id, case.request.borrower_id, case.status, case.storage_version, case.model_dump_json()))
            db.execute("INSERT INTO credit_sessions VALUES(?,?,?)", (actor.actor_id, message.session_id, case.case_id))
        return case

    @staticmethod
    def message_hash(message: MessageInput) -> str:
        return hashlib.sha256(message.model_dump_json().encode()).hexdigest()

    def receipt(self, message: MessageInput, actor: ActorContext) -> DialogueResult | None:
        with self.connect() as db:
            row = db.execute("SELECT input_hash,result FROM credit_receipts WHERE owner_id=? AND session_id=? AND message_id=?", (actor.actor_id, message.session_id, message.message_id)).fetchone()
        if not row:
            return None
        if row["input_hash"] != self.message_hash(message):
            raise ConflictError("message_id уже использован для другого содержимого")
        result = DialogueResult.model_validate_json(row["result"])
        self.load(result.case_id, actor)  # Recheck current permissions before replay.
        return result

    def commit(self, case: Case, expected_version: int, message: MessageInput, result: DialogueResult) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            case.storage_version = expected_version + 1
            cursor = db.execute("UPDATE credit_cases SET borrower_id=?,status=?,version=?,payload=? WHERE case_id=? AND version=?", (case.request.borrower_id, case.status, case.storage_version, case.model_dump_json(), case.case_id, expected_version))
            if cursor.rowcount != 1:
                raise ConflictError("Версия кейса изменилась; обновите состояние")
            db.execute("INSERT INTO credit_receipts VALUES(?,?,?,?,?)", (case.owner_id, message.session_id, message.message_id, self.message_hash(message), result.model_dump_json()))
            db.execute("INSERT INTO credit_audit(case_id,revision,correlation_id,message_id,event_at,payload) VALUES(?,?,?,?,?,?)", (case.case_id, case.revision, case.correlation_id, message.message_id, utcnow().isoformat(), result.model_dump_json()))
