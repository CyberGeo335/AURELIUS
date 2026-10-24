"""Choose questions deterministically; ML configuration gaps belong to engineering."""
from ..schemas.models import Case, FIELD_LABELS
from ..schemas.resolution import DataGap, DataResolutionPlan

QUESTIONS = {
    'legal_form': 'Какая форма бизнеса: ИП, ООО, АО или другая?',
    'purpose': 'На что нужны деньги?',
    'amount_rub': 'Какая сумма нужна в рублях? Укажите положительное целое число.',
    'term_months': 'На сколько месяцев нужны деньги? Укажите целое число от 1 до 600.',
    'borrower_id': 'Выберите компанию через доверенный интерфейс приложения.',
    'recurring': 'Это разовая потребность или повторяющиеся закупки?',
    'financing_need': 'Уточните характер потребности: разовая закупка, повторные закупки или иной вариант?',
}


def build_resolution(case: Case) -> DataResolutionPlan:
    issues = {issue.field:issue for issue in case.pending_clarifications}
    fields = list(dict.fromkeys([*issues, *case.missing_required]))
    gaps = []
    explicit_ready=bool(case.assessment and case.assessment.get('status')=='DEMO_ESTIMATE'
                        and case.assessment.get('evidence_ref')==case.result_refs.get('evidence'))
    for field in fields:
        issue = issues.get(field)
        status = ('CONFLICT' if issue.code == 'CONFLICT' else 'INVALID' if issue.code == 'INVALID_VALUE' else 'UNGROUNDED') if issue else 'MISSING'
        gaps.append(DataGap(field=field, status=status,
            resolution='DATABASE_THEN_USER' if field == 'legal_form' else 'ASK_USER',
            question=QUESTIONS.get(field, f"Уточните: {FIELD_LABELS.get(field, field)}."),
            reason=issue.code if issue else 'Значение не указано и не подтверждено источником'))
    if case.product_selection:
        for candidate in case.product_selection.candidates:
            if any(check.code == 'CARD_VALIDITY' and check.status == 'UNKNOWN' for check in candidate.checks):
                gaps.append(DataGap(field=f'product_terms:{candidate.product_id}',status='UNCONFIGURED',resolution='ENGINEERING',
                    reason='Нужны подтверждение утверждения кредитором, версия и даты действия условий. Ответ клиента их не подтверждает.'))
    if case.data_context:
        for item in case.data_context.get('questionnaire',[]):
            if item['status']=='MISSING':
                gaps.append(DataGap(field=f"questionnaire:{item['product_code']}:{item['field_code']}",status='MISSING',
                                    resolution='ASK_USER',question=item['question'],reason='Обязательное поле анкеты не заполнено'))
        for issue in case.data_context['data_quality']['blocking_issues']:
            if explicit_ready and issue=='ML_MAPPING_AND_FORMULAS_NOT_APPROVED':
                continue  # Explicit reviewed inputs do not claim automatic feature derivation.
            if issue in {'REQUEST_COMPANY_LEGAL_FORM_CONFLICT','LEGAL_FORM_SOURCE_CONFLICT'}:
                gaps.append(DataGap(field='legal_form',status='CONFLICT',resolution='ASK_USER',
                    question='Форма бизнеса в источниках или запросе расходится. Уточните выбранную компанию и предоставьте актуальное подтверждение формы.',
                    reason=issue))
            else:
                gaps.append(DataGap(field=issue, status='UNCONFIGURED', resolution='ENGINEERING',
                                    reason='Требуется настройка данных/контракта; ответ пользователя не утверждает модельную формулу'))
    return DataResolutionPlan(gaps=gaps, database_lookup=case.profile_lookup_status,
                              ready_for_product_matching=not fields,
                              ready_for_scoring=explicit_ready and not fields)
