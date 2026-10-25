import json
from personalCab.prom_v2.adapters import OllamaExtraction
from personalCab.prom_v2.agent import Agent
from personalCab.prom_v2.models import Actor, Command
from personalCab.prom_v2.repository import MemoryRepository

actor = Actor(actor_id="synthetic-v2-live", company_id=40, borrower_id="synthetic-business-40")
agent = Agent(MemoryRepository(), extractor=OllamaExtraction())
case = agent.handle(actor, Command(request_id="create", action="CREATE", expected_version=0))
proposal = agent.handle(actor, Command(request_id="chat", action="CHAT", case_id=case.case_id,
                                      expected_version=case.version,
                                      text="Я ИП. Нужно 1500000 рублей на закупку товара на 12 месяцев."))
assert proposal.pending is not None, proposal.error_code
assert proposal.request.amount_rub is None
assert proposal.pending.patch["amount_rub"] == 1500000
assert proposal.pending.patch["term_months"] == 12
confirmed = agent.handle(actor, Command(request_id="confirm", action="CONFIRM_FACTS", case_id=case.case_id,
                                       expected_version=proposal.version,
                                       arguments={"proposal_id": proposal.pending.proposal_id}))
assert confirmed.request.amount_rub == 1500000 and confirmed.request.term_months == 12
invalid = agent.handle(actor, Command(request_id="invalid", action="CHAT", case_id=case.case_id,
                                     expected_version=confirmed.version, text="Измени сумму на -100 рублей"))
assert invalid.request.amount_rub == 1500000
assert any(gap.field == "amount_rub" and gap.status == "INVALID" for gap in invalid.data_resolution.gaps)
answer = agent.handle(actor, Command(request_id="rag", action="CHAT", case_id=case.case_id,
                                    expected_version=invalid.version, text="Какой формат ИНН для R01 ООО?"))
assert answer.knowledge_answer.status == "FOUND"
assert answer.request == invalid.request and answer.revision == invalid.revision
print(json.dumps({"live_model": "gpt-oss:20b", "proposal_confirmation": "passed", "invalid_update": "preserved",
                  "rag": "FOUND", "v1_writes": False}, ensure_ascii=False))
