"""Use the existing V2 graph/extractor, bound to a cabinet draft and cookie user.

Only CHAT/CONFIRM_FACTS enter the graph. No legacy repositories, bank modules,
consent commands, submission commands or user credentials enter this boundary.
"""
from psycopg.types.json import Jsonb
from .declared_facts import COMPANY_TARGETS


def company_request_field(target):
    # Some catalog rows combine the code and its descriptive name.
    target = target.removeprefix('public.').split(' + ')[0]
    return next((field for field, column in COMPANY_TARGETS.items() if column == target), None)

PURPOSES = {
    'INVENTORY': 'Закупка товаров', 'WORKING_CAPITAL': 'Пополнение оборотных средств',
    'INVESTMENT': 'Развитие бизнеса', 'REAL_ESTATE': 'Покупка недвижимости',
    'VEHICLE': 'Покупка транспорта', 'REFINANCING': 'Рефинансирование',
    'GUARANTEE': 'Обеспечение контракта', 'OTHER': 'Другая цель',
}
NEEDS = {
    'ONE_TIME_PURCHASE': 'разовая закупка', 'DEVELOPMENT': 'развитие бизнеса',
    'STATE_SUPPORT': 'проект с господдержкой', 'REPEATED_PURCHASES': 'регулярные закупки',
    'VEHICLE': 'покупка транспорта', 'CASH_GAP': 'кассовый разрыв',
    'CARD_EXPENSES': 'повседневные расходы по карте', 'PREMISES': 'покупка помещения',
    'PROPERTY_BACKED': 'финансирование под залог имущества', 'REFINANCING': 'рефинансирование долга',
    'SMALL_TRANCHES': 'небольшие транши', 'RESERVE': 'резервный лимит',
    'MARKETPLACE': 'работа на маркетплейсе', 'PARTNER_PURCHASE': 'закупка у партнёра',
    'CONTRACT_SECURITY': 'обеспечение контракта', 'EQUIPMENT_USE': 'использование оборудования',
    'DEFERRED_PAYMENT': 'поставка с отсрочкой платежа',
}


class DraftRepository:
    """Unit of work inside Cabinet's locked, idempotent PostgreSQL transaction."""
    durable = True

    def __init__(self, case):
        self.case = case

    def transact(self, actor, command, handler):
        from .repository import authorize, check_version
        authorize(self.case, actor)
        check_version(self.case, command)
        return handler(self.case)


def dialogue_view(payload):
    if not payload:
        return None
    from .models import Case
    case = Case.model_validate(payload)
    pending = case.pending.model_dump(mode='json') if case.pending else None
    if pending:
        labels = {**PURPOSES, **NEEDS, 'IP': 'ИП', 'OOO': 'ООО', 'AO': 'АО', 'OTHER': 'Другое'}
        pending['display_values'] = {key: ('Да' if value else 'Нет') if isinstance(value, bool)
                                     else labels.get(value, str(value)) if isinstance(value, str) else str(value)
                                     for key, value in pending['patch'].items()}
    return {'history': case.history, 'pending': pending,
            'problems': [p.model_dump(mode='json') for p in case.problems]}


def run_dialogue(cabinet, db, user, app, body, meta):
    from .cabinet import ApiError
    from .agent import Agent
    from .adapters import OllamaExtraction, CatalogProducts, ReferenceKnowledge
    from .models import Actor, Case, Command, LoanRequest, Action

    cabinet.client(user)
    if app['application_status'] != 'DRAFT':
        raise ApiError(409, 'Диалог заполняет только черновик. Для дозапроса используйте отдельный ответ.')
    aid = app['application_id']
    actor = Actor(actor_id=str(user['user_id']), borrower_id=f"company:{app['company_id']}", company_id=app['company_id'])
    row = db.execute('SELECT payload FROM aurelius_cabinet.dialogues WHERE application_id=%s AND user_id=%s FOR UPDATE', (aid, user['user_id'])).fetchone()
    case = Case.model_validate(row['payload']) if row else Case(
        case_id=f"cabinet:{aid}:user:{user['user_id']}", owner_id=actor.actor_id,
        company_id=actor.company_id, borrower_id=actor.borrower_id,
        request=LoanRequest(borrower_id=actor.borrower_id), version=1)
    # Canonical DB form wins over stale dialogue state on every turn. Never take
    # loan amounts/terms from historical company applications.
    company = db.execute('SELECT inn,entity_type,information_reliability_status FROM public.companies WHERE company_id=%s', (app['company_id'],)).fetchone()
    requirements = db.execute('SELECT * FROM public.application_field_requirements WHERE product_code=%s ORDER BY field_number', (app['product_code'],)).fetchall()
    applicable = [r for r in requirements if r['required_ip' if company['entity_type'] == 'INDIVIDUAL_ENTREPRENEUR' else 'required_ooo']]
    values = case.request.model_dump()
    values['amount_rub'] = int(app['requested_amount']) if app['requested_amount'] is not None and app['requested_amount'] == int(app['requested_amount']) else None
    values['term_months'] = app['requested_term_months']
    reverse = {v: k for k, v in PURPOSES.items()}
    # Preserve arbitrary free-text purpose in the public form. An enum mismatch
    # is a clarification, not permission to replace that text.
    values['purpose'] = reverse.get(app['purpose'])
    fields = {r['field_code']: r['field_value'] for r in db.execute('SELECT field_code,field_value FROM public.application_field_values WHERE application_id=%s', (aid,))}
    legal = {'ООО': 'OOO', 'OOO': 'OOO', 'АО': 'AO', 'AO': 'AO', 'ИП': 'IP', 'IP': 'IP', 'Другая форма': 'OTHER'}
    for requirement in applicable:
        field = company_request_field(requirement['target_db_field'])
        value = fields.get(requirement['field_code'])
        if field and requirement['field_code'] in fields and value in (None, ''):
            values[field] = None
            continue
        if field and value not in (None, ''):
            candidate = legal.get(value) if field == 'legal_form' else value
            try:
                parsed = LoanRequest.model_validate({field: candidate})
            except ValueError:
                continue
            if candidate is not None:
                values[field] = getattr(parsed, field)
    if company['information_reliability_status'] == 'VERIFIED':
        if company['inn']:
            values['inn'] = company['inn']
        if company['entity_type'] == 'INDIVIDUAL_ENTREPRENEUR':
            values['legal_form'] = 'IP'
    case.request = LoanRequest.model_validate(values)
    case.selected_product_id = {'R01': 'term', 'R02': 'rcl', 'R03': 'overdraft'}[app['product_code']]
    if row is None:
        case.history.append({'role': 'assistant', 'content': 'Диалог связан с этой заявкой и вашей компанией. Предложенные изменения требуют отдельного подтверждения.'})
    if app['purpose'] and values['purpose'] is None:
        context = f"Сохранённая цель анкеты: {app['purpose']}. Она сохраняется до явного подтверждения изменения."
        if not case.history or case.history[-1]['content'] != context:
            case.history.append({'role': 'assistant', 'content': context})
    if cabinet.dialogue_dependencies is None:
        cabinet.dialogue_dependencies = (OllamaExtraction(), CatalogProducts(), ReferenceKnowledge())
    extractor, products, knowledge = cabinet.dialogue_dependencies
    agent = Agent(DraftRepository(case), extractor=extractor, products=products, knowledge=knowledge)
    action = Action.CHAT if body['action'] == 'chat' else Action.CONFIRM_FACTS
    if action == Action.CHAT:
        text = body.get('text')
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 12000:
            raise ApiError(400, 'Введите сообщение до 12000 символов.')
        command = Command(request_id=body['request_id'], action=action, case_id=case.case_id, expected_version=case.version, text=text)
    else:
        if not case.pending or case.pending.proposal_id != body.get('proposal_id'):
            raise ApiError(409, 'Предложение изменилось. Проверьте актуальные сведения.', 'STALE_PROPOSAL')
        if case.pending.clear_fields:
            raise ApiError(409, 'Удаление сведений требует отдельного редактирования формы. Уточните сообщение без удаления.')
        if 'inn' in case.pending.patch and company['inn'] and case.pending.patch['inn'] != company['inn']:
            raise ApiError(409, 'ИНН не совпадает с вашей компанией. Требуется проверка сотрудника.')
        legal = case.pending.patch.get('legal_form')
        if legal and ((legal == 'IP') != (company['entity_type'] == 'INDIVIDUAL_ENTREPRENEUR')):
            raise ApiError(409, 'Форма бизнеса отличается от записи компании. Требуется проверка сотрудника.')
        command = Command(request_id=body['request_id'], action=action, case_id=case.case_id, expected_version=case.version,
                          arguments={'proposal_id': body['proposal_id']})
    proposed = dict(case.pending.patch) if case.pending else {}
    view = agent.handle(actor, command)
    if action == Action.CHAT and view.error_code == 'EXTRACTION_INVALID':
        raise ApiError(503, 'Ollama не вернула проверяемые сведения. Повторите сообщение или заполните форму.', 'EXTRACTION_UNAVAILABLE')
    if action == Action.CONFIRM_FACTS:
        fields, patch = {}, {}
        code = app['product_code']
        for field, value in proposed.items():
            # Only independently accepted fields can reach the public form.
            if case.request.model_dump(mode='json').get(field) != value:
                continue
            if field == 'amount_rub':
                patch['amount'] = value
                fields[code + '_05'] = str(value)
            elif field == 'term_months':
                patch['term'] = value
                fields[code + '_06'] = str(value)
            elif field == 'purpose':
                patch['purpose'] = PURPOSES[value]
                fields[code + '_04'] = PURPOSES[value]
            elif field in COMPANY_TARGETS:
                display = {'IP': 'ИП', 'OOO': 'ООО', 'AO': 'АО', 'OTHER': 'Другая форма'}.get(value, value) if field == 'legal_form' else str(value)
                for requirement in applicable:
                    if company_request_field(requirement['target_db_field']) == field:
                        fields[requirement['field_code']] = display
            if field == 'legal_form':
                for requirement in applicable:
                    if requirement['target_db_field'] == 'companies.entity_type':
                        fields[requirement['field_code']] = 'ИП' if value == 'IP' else 'Юридическое лицо'
        if patch or fields:
            cabinet.save(db, app, {**patch, 'fields': fields}, meta['form_state'])
        case.history[-1]['content'] = 'Подтверждённые поля анкеты сохранены. Сведения о характере потребности сохранены в диалоге. Проверьте оставшиеся поля анкеты. ' + case.history[-1]['content']
    pending = case.pending.patch if case.pending else {}
    if action == Action.CHAT and (pending.get('purpose', case.request.purpose) is None or pending.get('financing_need', case.request.financing_need) is None):
        cards = products.matcher.catalog.products
        suggestions = '; '.join(f"{card.name}: {', '.join(NEEDS[need] for need in card.needs)}" for card in cards)
        # Names and use cases come only from the existing 16-direction catalog.
        case.history[-1]['content'] += ' Если пока не знаете цель или характер потребности, выберите направление и опишите пример задачи: ' + suggestions + '. Для части направлений потребуется отдельное обращение к сотруднику.'
    current_fields = {r['field_code']: r['field_value'] for r in db.execute(
        'SELECT field_code,field_value FROM public.application_field_values WHERE application_id=%s', (aid,))}
    for requirement in applicable:
        field = company_request_field(requirement['target_db_field'])
        if (field and current_fields.get(requirement['field_code']) in (None, '')
                and getattr(case.request, field) is None and pending.get(field) is None):
            case.history[-1]['content'] += ' Укажите недостающий реквизит: ' + requirement['field_label'] + '. Можно сообщить его помощнику или заполнить в форме.'
            break
    db.execute('INSERT INTO aurelius_cabinet.dialogues(application_id,user_id,company_id,payload) VALUES(%s,%s,%s,%s) ON CONFLICT(application_id,user_id) DO UPDATE SET payload=EXCLUDED.payload,updated_at=now()',
               (aid, user['user_id'], app['company_id'], Jsonb(case.model_dump(mode='json'))))
