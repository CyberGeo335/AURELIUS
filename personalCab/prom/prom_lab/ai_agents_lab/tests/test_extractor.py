from ..agents.factory import OllamaExtractor, extraction_schema
from ..schemas.models import Case, Extraction, LoanRequest, MessageInput


def test_schema_requires_explicit_nullable_patch():
    schema = extraction_schema()
    assert "patch" in schema["required"]
    request_schema = schema["$defs"]["LoanRequest"]
    assert set(request_schema["required"]) == set(LoanRequest.model_fields)
    assert "null" in str(request_schema["properties"]["amount_rub"])


def test_bad_quote_is_corrected_before_state_changes():
    bad = Extraction(patch=LoanRequest(purpose="INVENTORY"), evidence={"purpose": "закупка товара"}).model_dump(mode="json")
    good = Extraction(patch=LoanRequest(purpose="INVENTORY"), evidence={"purpose": "закупку товара"}).model_dump(mode="json")
    class FixtureChain:
        def __init__(self):
            self.responses = [bad, good]
            self.calls = 0
        def invoke(self, messages):
            self.calls += 1
            return self.responses.pop(0)
    extractor = object.__new__(OllamaExtractor)
    extractor.chain = FixtureChain()
    result = extractor.extract(MessageInput(session_id="s", message_id="m", text="Нужно на закупку товара"), Case(owner_id="test"))
    assert result.patch.purpose == "INVENTORY" and extractor.chain.calls == 2


def test_amount_change_mislabelled_cancel_does_not_cancel():
    response = Extraction(intent="CANCEL", patch=LoanRequest(amount_rub=5000000), evidence={"amount_rub": "пять миллионов", "intent": "Измени сумму"}).model_dump(mode="json")
    class FixtureChain:
        def invoke(self, messages):
            return response
    extractor = object.__new__(OllamaExtractor)
    extractor.chain = FixtureChain()
    result = extractor.extract(MessageInput(session_id="s", message_id="m", text="Измени сумму на пять миллионов"), Case(owner_id="test", request=LoanRequest(amount_rub=3000000)))
    assert result.intent == "PROVIDE_DETAILS" and result.patch.amount_rub == 5000000


def test_unchanged_restatements_need_no_new_provenance():
    response = Extraction(patch=LoanRequest(legal_form="IP", amount_rub=5000000), evidence={"amount_rub": "пять миллионов"}).model_dump(mode="json")
    class FixtureChain:
        def invoke(self, messages):
            return response
    extractor = object.__new__(OllamaExtractor)
    extractor.chain = FixtureChain()
    result = extractor.extract(MessageInput(session_id="s", message_id="m", text="Теперь пять миллионов"), Case(owner_id="test", request=LoanRequest(legal_form="IP", amount_rub=3000000)))
    assert result.patch.legal_form is None and result.patch.amount_rub == 5000000


def test_goal_change_cannot_silently_clear_known_purpose():
    text='Измени цель: покупка автомобиля для бизнеса'
    bad=Extraction(clear_fields=['purpose'],evidence={'purpose':text}).model_dump(mode='json')
    good=Extraction(patch=LoanRequest(purpose='VEHICLE',financing_need='VEHICLE'),evidence={'purpose':text,'financing_need':text}).model_dump(mode='json')
    class FixtureChain:
        def __init__(self):
            self.responses=[bad,good]
            self.calls=0
        def invoke(self,messages):
            self.calls+=1
            return self.responses.pop(0)
    extractor=object.__new__(OllamaExtractor)
    extractor.chain=FixtureChain()
    result=extractor.extract(MessageInput(session_id='s',message_id='m',text=text),Case(owner_id='test',request=LoanRequest(purpose='INVENTORY')))
    assert result.patch.purpose=='VEHICLE' and not result.clear_fields and extractor.chain.calls==2
