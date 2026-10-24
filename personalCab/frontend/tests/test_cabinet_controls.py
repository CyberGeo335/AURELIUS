from uuid import uuid4

import pytest

from personalCab.frontend.server import ChatService,ChatCommand,CaseCommand
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import Extraction,LoanRequest,Scope
from personalCab.prom.prom_lab.ai_agents_lab.repositories.case_repository import AccessDenied,ConflictError


class Extractor:
    def extract(self,message,case):
        if 'отмени' in message.text.casefold():return Extraction(intent='CANCEL',evidence={'intent':message.text})
        return Extraction(patch=LoanRequest(amount_rub=3000000),evidence={'amount_rub':message.text})


def test_cancel_then_new_request_creates_new_case_and_preserves_old(tmp_path):
    service=ChatService(tmp_path/'cases.db',extractor=Extractor())
    token,actor,session,_=service.client(None)
    canceled=service.handle(ChatCommand(message_id='cancel',text='Отмени обращение'),actor,session)
    next_case=service.handle(ChatCommand(message_id='new',text='Новая заявка, нужно 3000000 рублей'),actor,session)
    assert canceled['result']['status']=='CANCELLED'
    assert canceled['result']['case_id']!=next_case['result']['case_id']
    _,actor,new_session,_=service.client(token)
    assert new_session!=session
    replay=service.handle(ChatCommand(message_id='new',text='Новая заявка, нужно 3000000 рублей'),actor,new_session)
    assert replay==next_case
    assert len(service.controls.applications(actor))==2


def test_control_receipts_consent_revocation_and_company_allowlist(tmp_path):
    service=ChatService(tmp_path/'cases.db',company_id=40,allowed_company_ids=[40,41])
    token,actor,session,_=service.client(None)
    command={'scope':Scope.EVIDENCE_COLLECTION.value,'granted':True}
    first=service.controls.execute(actor,session,'grant','consent',command)
    assert service.controls.execute(actor,session,'grant','consent',command)==first
    with pytest.raises(ConflictError):service.controls.execute(actor,session,'grant','consent',{**command,'granted':False})
    _,actor,session,_=service.client(token)
    assert actor.has_consent(Scope.EVIDENCE_COLLECTION,actor.active_borrower_id)
    service.controls.execute(actor,session,'revoke','consent',{**command,'granted':False})
    _,actor,session,_=service.client(token)
    assert not actor.has_consent(Scope.EVIDENCE_COLLECTION,actor.active_borrower_id)
    with pytest.raises(AccessDenied):service.controls.execute(actor,session,'foreign','company',{'company_id':42})
    service.controls.execute(actor,session,'switch','company',{'company_id':41})
    _,actor,session,_=service.client(token)
    assert actor.company_id==41 and not actor.consents


def test_form_and_chat_use_same_case_without_llm_for_structured_edit(tmp_path):
    service=ChatService(tmp_path/'cases.db',extractor=Extractor())
    _,actor,session,_=service.client(None)
    first=service.handle(ChatCommand(message_id='first',text='Нужно 3000000 рублей'),actor,session)
    updated=service.handle(CaseCommand(message_id='form',text='Обновить параметры',command='UPDATE_REQUEST',
                                      arguments={'patch':{'amount_rub':5000000,'term_months':36}}),actor,session)
    assert updated['result']['case_id']==first['result']['case_id']
    assert updated['result']['revision']>first['result']['revision']
    assert service.controls.applications(actor)[0]['request']['amount_rub']==5000000
    assert service.state(actor,session)['latest']['result']['request']['term_months']==36
    with pytest.raises(ConflictError):service.controls.execute(actor,session,'new','new_session',{})
