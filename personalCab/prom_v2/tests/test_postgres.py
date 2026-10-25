"""Optional persistence check on an explicitly dedicated seeded test database."""
from dataclasses import replace
import os
from uuid import uuid4

import pytest

from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_config import PostgresConfig
from personalCab.prom_v2.agent import Agent
from personalCab.prom_v2.models import Actor, Command
from personalCab.prom_v2.repository import PostgresRepository, Conflict


@pytest.mark.skipif(not os.getenv("AURELIUS_TEST_DATABASE_URL"), reason="Dedicated seeded test DB not configured")
def test_v2_restores_case_receipt_and_keeps_v1_schema_separate():
    config = replace(PostgresConfig.from_env(), conninfo=os.environ["AURELIUS_TEST_DATABASE_URL"])
    repository = PostgresRepository(config)
    repository.initialize()
    actor = Actor(actor_id="test-v2-" + uuid4().hex, company_id=40, borrower_id="test-business-40")
    create = Command(request_id="create", action="CREATE", expected_version=0)
    agent = Agent(repository)
    first = agent.handle(actor, create)
    edit = Command(request_id="edit", action="UPDATE_REQUEST", case_id=first.case_id,
                   expected_version=first.version, arguments={"patch": {"amount_rub": 1500000}})
    updated = agent.handle(actor, edit)
    reopened = Agent(PostgresRepository(config))
    assert reopened.handle(actor, edit) == updated
    assert reopened.state(actor, updated.case_id).request.amount_rub == 1500000
    with pytest.raises(Conflict):
        reopened.handle(actor, edit.model_copy(update={"request_id": "stale"}))
    with config.connect() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM aurelius_agent_v2.audit WHERE case_id=%s", (first.case_id,)).fetchone()["n"] == 2
        assert db.execute("SELECT COUNT(*) AS n FROM aurelius_workflow.credit_cases WHERE case_id=%s", (first.case_id,)).fetchone()["n"] == 0
