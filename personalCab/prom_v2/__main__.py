"""Run V2 explicitly. No V1 startup, schema migration or WEB switch is implicit."""
import argparse
from dataclasses import replace
import json
import os
import sys
from uuid import uuid4

from .adapters import OllamaExtraction
from .agent import Agent
from .models import Action, Actor, Command
from .repository import AccessDenied, Conflict, MemoryRepository, PostgresRepository


def main():
    parser = argparse.ArgumentParser(description="Independent AURELIUS V2 agent · DEMO")
    parser.add_argument("--memory", action="store_true", help="Explicit volatile demo/test mode; never a DB fallback")
    parser.add_argument("--init-db", action="store_true", help="Create only aurelius_agent_v2 tables")
    parser.add_argument("--actor-id")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--borrower-id")
    parser.add_argument("--with-ollama", action="store_true", help="Enable reviewed Ollama extraction adapter")
    parser.add_argument("--question", help="One-shot reference question; no LLM required")
    parser.add_argument("--serve", action="store_true", help="Local scoped-token API; otherwise read JSONL commands")
    parser.add_argument("--port", type=int, default=5180)
    args = parser.parse_args()
    if args.memory and args.init_db:
        parser.error("--init-db requires PostgreSQL")
    if args.serve and args.question:
        parser.error("--serve and --question are separate modes")
    if args.memory:
        repository = MemoryRepository()
    else:
        from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_config import PostgresConfig
        config = PostgresConfig.from_env()
        if os.getenv("AURELIUS_V2_DATABASE_URL"):
            config = replace(config, conninfo=os.environ["AURELIUS_V2_DATABASE_URL"])
        repository = PostgresRepository(config)
    if args.init_db:
        repository.initialize()
        print(json.dumps({"schema": "aurelius_agent_v2", "initialized": True}))
        return
    if not args.actor_id or not args.company_id or not args.borrower_id:
        parser.error("Trusted --actor-id, --company-id and --borrower-id are required")
    actor = Actor(actor_id=args.actor_id, company_id=args.company_id, borrower_id=args.borrower_id)
    agent = Agent(repository, extractor=OllamaExtraction() if args.with_ollama else None)
    if args.question:
        if not agent.knowledge.is_question(args.question):
            parser.error("--question accepts only reference questions, not case mutations")
        created = agent.handle(actor, Command(request_id=uuid4().hex, action=Action.CREATE, expected_version=0))
        result = agent.handle(actor, Command(request_id=uuid4().hex, action=Action.CHAT,
                                            case_id=created.case_id, expected_version=created.version, text=args.question))
        print(result.model_dump_json(indent=2))
        return
    if args.serve:
        from .server import serve
        serve(agent, actor, os.getenv("AURELIUS_V2_API_TOKEN", ""), args.port)
        return
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            command = Command.model_validate_json(line)
            print(agent.handle(actor, command).model_dump_json(), flush=True)
        except (ValueError, Conflict, AccessDenied) as exc:
            print(json.dumps({"error": type(exc).__name__}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
