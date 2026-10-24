from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .agents.workflow import WorkflowApp
from .repositories.case_repository import AccessDenied, ConflictError
from .schemas.models import ActorContext, Consent, MessageInput, Scope


def main():
    parser = argparse.ArgumentParser(description="AURELIUS module 1 — local DEMO dialogue and workflow")
    parser.add_argument("text", nargs="+", help="Сообщение предпринимателя")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--message-id", default=None, help="Повторите тот же id для идемпотентного повтора")
    parser.add_argument("--actor-id", default="demo-petya")
    parser.add_argument("--borrower-id", default=None)
    parser.add_argument("--allowed-borrower-id", action="append", default=[])
    parser.add_argument("--role", choices=["BORROWER", "OPERATOR", "READER"], default="BORROWER")
    parser.add_argument("--consents-file", type=Path, help="Доверенный DEMO JSON-массив согласий; текст чата не выдаёт согласия")
    parser.add_argument("--deny-scope", action="append", choices=list(Scope), default=[])
    parser.add_argument("--document-ref", action="append", default=[])
    parser.add_argument("--database", type=Path, default=None, help="Явный legacy SQLite режим")
    parser.add_argument("--company-id", type=int, help="Доверенная привязка к PostgreSQL company_id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        consents = [Consent.model_validate(c) for c in json.loads(args.consents_file.read_text())] if args.consents_file else []
        actor = ActorContext(actor_id=args.actor_id, role=args.role, company_id=args.company_id,
                             allowed_borrower_ids=args.allowed_borrower_id or ([args.borrower_id] if args.borrower_id else []),
                             active_borrower_id=args.borrower_id, consents=consents, denied_scopes=args.deny_scope)
        message = MessageInput(session_id=args.session_id, message_id=args.message_id or uuid4().hex,
                               text=" ".join(args.text), document_refs=args.document_ref)
        with WorkflowApp(args.database) as app:
            result = app.handle(message, actor)
        if args.json:
            print(result.model_dump_json(indent=2))
        else:
            print(f"DEMO · {result.case_id} · revision={result.revision} · {result.status}")
            print(result.message)
            print(f"message_id={message.message_id}; next_action={result.next_action}")
    except (AccessDenied, ConflictError, ValidationError, ValueError) as exc:
        parser.exit(2, f"Ошибка: {exc}\n")


if __name__ == "__main__":
    main()
