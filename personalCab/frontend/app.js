'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
let drafts = [];
let currentResult = null;
let currentContext = null;
let shownConsentHint = null;
let selectedProductCode = 'R01';
let pendingCaseCommand = null;
let editingId = null;
let pendingAttachment = null;
let documents = [];
let toastTimer;
const rubles = amount => new Intl.NumberFormat('ru-RU', {maximumFractionDigits:0}).format(amount) + ' ₽';
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function toast(message) {
  $('.toast').textContent = message;
  $('.toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('.toast').hidden = true; }, 4000);
}
async function loadApplications() {
  const data = await api('/api/applications');
  drafts = data.applications.map(item => ({id:item.case_id,name:item.request.project_name || 'Запрос на финансирование',amount:item.request.amount_rub,term:item.request.term_months,purpose:item.request.purpose,legal_form:item.request.legal_form,status:item.status,stage:item.completed_module,application_ids:item.application_ids}));
  drafts.sort((a,b)=>Number(b.id===currentResult?.case_id)-Number(a.id===currentResult?.case_id));
  renderApplications();
}
const viewLabels = {overview:'Обзор бизнеса',applications:'Мои заявки',documents:'Документы',company:'Моя компания'};
function showView(view) {
  if (!viewLabels[view]) return;
  $$('.view').forEach(section => { section.hidden = section.id !== `view-${view}`; });
  $$('.nav-item').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
  });
  $('#breadcrumb-current').textContent = viewLabels[view];
  document.title = `AURELIUS — ${viewLabels[view]}`;
  closeMenu();
  window.scrollTo({top:0,behavior:'instant'});
}
$$('[data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
function renderApplications() {
  $('#application-count').textContent = String(drafts.length);
  const latest = drafts[0];
  if (!latest) {
    $('#overview-application-number').textContent='Заявка ещё не создана';
    $('#overview-amount').textContent='—'; $('#overview-term').textContent='—';
    $('#applications-list').textContent='Создайте запрос через форму или ассистента. Он будет сохранён на сервере.';
    $('#view-overview .application-card .status').textContent='Нет заявки';
    $('#view-overview .progress-label').textContent='Начните с запроса в чате или форме';
    return;
  }
  $('#overview-application-number').textContent = `Заявка № ${latest.id}`;
  $('.application-top h3').textContent = latest.name;
  $('#overview-amount').textContent = latest.amount===null?'Не указано':rubles(latest.amount);
  $('#overview-term').textContent = latest.term===null?'Не указано':`${latest.term} мес.`;
  $('#view-overview .application-card .status').textContent=latest.status;
  $('#view-overview .progress-label').textContent=`Этап ${latest.stage} из 5 · ${['','Запрос','Подбор','Данные','Оценка DEMO','Рассмотрение DEMO'][latest.stage]}`;
  $('#view-overview .progress-track').replaceChildren(...Array.from({length:5},(_,index)=>{const segment=document.createElement('span');segment.style.opacity=index<latest.stage?'1':'.15';return segment;}));
  $('#applications-list').innerHTML = drafts.map(item => `<article class="application-card application-list-item"><div class="application-top"><div class="product-icon"><img src="front_assets/money.svg" alt=""></div><div><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.id)}</p></div><span class="status">${escapeHtml(item.status)}</span></div><div class="application-data"><div><small>Сумма запроса</small><strong>${item.amount===null?'Не указано':rubles(item.amount)}</strong></div><div><small>Срок</small><strong>${item.term===null?'Не указано':item.term+' мес.'}</strong></div><button class="button button-secondary" data-edit-id="${escapeHtml(item.id)}">Открыть →</button></div><p class="application-purpose">${escapeHtml(item.purpose || 'Цель не указана')} · DEMO · ${escapeHtml(JSON.stringify(item.application_ids))}</p></article>`).join('');
}
async function openApplication(draft) {
  if(!draft && currentResult){
    if(!['CANCELLED','COMPLETED'].includes(currentResult.status)){toast('Продолжите текущую заявку или отмените её перед созданием новой.');openChat();return;}
    try{await control('/api/session/new',{});await refreshAssistant();}catch(error){toast(error.message);return;}
  }
  editingId = draft?.id ?? null;
  $('#application-name').value = draft?.name ?? '';
  $('#application-amount').value = draft?.amount ?? 3000000;
  $('#application-term').value = String(draft?.term ?? 24);
  $('#application-purpose').value = draft?.purpose ?? 'WORKING_CAPITAL';
  $('#application-legal-form').value = draft?.legal_form ?? '';
  $('#application-inn').value=currentResult?.request.inn ?? '';
  $('#application-tranche-days').value=currentResult?.request.tranche_term_days ?? '';
  $('#application-tranche-months').value=currentResult?.request.tranche_term_months ?? '';
  $('#application-drawdown-months').value=currentResult?.request.drawdown_period_months ?? '';
  $('#application-dialog').showModal();
}
$$('[data-new-application]').forEach(button => button.addEventListener('click', () => openApplication()));
$('[data-edit-application]').addEventListener('click', () => openApplication(drafts[0]));
$('#applications-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-edit-id]');
  if (button) {
    try {
      await control('/api/applications/select',{case_id:button.dataset.editId});
      await refreshAssistant();
      const draft=drafts.find(item=>item.id===button.dataset.editId);
      if(['CANCELLED','COMPLETED'].includes(draft.status)){openChat();return;}
      openApplication(draft);
    }catch(error){toast(error.message);}
  }
});
$('#application-form').addEventListener('submit', async event => {
  event.preventDefault();
  const name = $('#application-name').value.trim();
  if (!name) { $('#application-name').setCustomValidity('Введите название проекта'); $('#application-name').reportValidity(); return; }
  try {
    const patch={project_name:name,amount_rub:Number($('#application-amount').value),term_months:Number($('#application-term').value),purpose:$('#application-purpose').value};
    if($('#application-legal-form').value)patch.legal_form=$('#application-legal-form').value;
    if($('#application-inn').value)patch.inn=$('#application-inn').value;
    for(const [id,field] of [['application-tranche-days','tranche_term_days'],['application-tranche-months','tranche_term_months'],['application-drawdown-months','drawdown_period_months']])if($('#'+id).value)patch[field]=Number($('#'+id).value);
    const envelope=await caseCommand('UPDATE_REQUEST',{patch},'Параметры заявки обновлены через форму');
    if(envelope.result.error_code)throw new Error(envelope.result.message);
    $('#application-dialog').close(); toast('Запрос сохранён на сервере и синхронизирован с чатом.');
  }catch(error){toast(error.message);}
});
$('#application-name').addEventListener('input',event => event.target.setCustomValidity(''));
$('[data-close-modal]').addEventListener('click', () => $('#application-dialog').close());
$('#application-dialog').addEventListener('click', event => {
  const r = event.currentTarget.getBoundingClientRect();
  if (event.target === event.currentTarget && (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom)) event.currentTarget.close();
});
const chat = $('#assistant-dialog');
const compact = matchMedia('(max-width: 1050px)');
if (compact.matches) { chat.removeAttribute('open'); document.body.classList.remove('chat-open'); }
function openChat() {
  if (!chat.open) {
    if (compact.matches) chat.showModal(); else chat.show();
  }
  document.body.classList.add('chat-open');
  $('#chat-input').focus();
  closeMenu();
}
function closeChat() { chat.close(); document.body.classList.remove('chat-open'); }
$$('[data-open-chat]').forEach(button => button.addEventListener('click', openChat));
$('#close-chat').addEventListener('click', closeChat);
chat.addEventListener('close', () => { if (!chat.open) document.body.classList.remove('chat-open'); });
compact.addEventListener('change', () => {
  const wasOpen = chat.open;
  if (wasOpen) { chat.close(); document.body.classList.remove('chat-open'); }
  if (!compact.matches && wasOpen) { chat.show(); document.body.classList.add('chat-open'); }
});
const initialWelcome = $('.chat-welcome').cloneNode(true);
const messages = $('#chat-messages');
let chatBusy = true;
let chatConnected = false;
let failedTurn = null;
let lastRevision = null;
function syncSend() {
  $('.send-button').disabled = chatBusy || !chatConnected || Boolean(failedTurn) || Boolean(pendingCaseCommand) || !$('#chat-input').value.trim();
  $('#new-chat').disabled = chatBusy;
  $('#attach-chat-file').disabled = chatBusy;
  $('#chat-input').readOnly = chatBusy;
  $('#start-new-case').disabled=chatBusy || Boolean(failedTurn) || Boolean(pendingCaseCommand) || (Boolean(currentResult) && !['CANCELLED','COMPLETED'].includes(currentResult.status));
  renderCaseControls();
}
function addMessage(text, kind, attachment) {
  if(kind==='assistant' && text==='Для следующего действия нужно действующее согласие выбранного субъекта. Оформите его в доверенном интерфейсе приложения. Зависимый запрос пока не выполнялся.')text='Заявка сохранена. Откройте «Согласия и данные бизнеса» над перепиской: там можно дать разрешение на получение сведений о вашем бизнесе и нажать «Обновить данные и анкету».';
  const message = document.createElement('div');
  message.className = `message ${kind}-message`;
  const label = document.createElement('small');
  label.textContent = kind === 'user' ? 'Вы' : kind === 'assistant' ? 'Бизнес-ассистент' : 'Системное сообщение';
  const content = document.createElement('p'); content.textContent = text;
  message.append(label,content);
  if (attachment) { const file = document.createElement('p'); file.className = 'attached'; file.textContent = `Файл: ${attachment.name} · будет сохранён как непроверенное подтверждение`; message.append(file); }
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}
const fieldLabels = {inn:'ИНН',project_name:'название проекта',borrower_id:'субъект',legal_form:'форма бизнеса',purpose:'цель',amount_rub:'сумма',term_months:'срок',needed_by:'дата потребности',repayment_source:'источник возврата',recurring:'повторяемость потребности',known_obligations:'обязательства',seasonality:'сезонность',collateral:'обеспечение',financing_need:'характер потребности',business_age_months:'возраст бизнеса, мес.',monthly_revenue_rub:'месячный оборот, ₽',operating_cycle_days:'оборотный цикл, дней',has_collateral:'наличие обеспечения',tranche_term_days:'срок транша, дней',tranche_term_months:'срок транша, месяцев',drawdown_period_months:'период выборки, месяцев'};
const purposeLabels = {INVENTORY:'Закупка товара',WORKING_CAPITAL:'Оборотные средства',INVESTMENT:'Инвестиции',REAL_ESTATE:'Недвижимость',VEHICLE:'Транспорт',REFINANCING:'Рефинансирование',GUARANTEE:'Гарантия',OTHER:'Другая цель'};
const legalLabels = {IP:'ИП',OOO:'ООО',AO:'АО',OTHER:'Другая форма'};
function appendWorkflowLog(envelope) {
  currentResult=envelope.result;
  const log = envelope.workflow_log;
  messages.querySelectorAll('.workflow-log').forEach(item=>item.remove());
  const details = document.createElement('details'); details.className='workflow-log'; details.open=true;
  const summary = document.createElement('summary'); summary.textContent=`Общий лог · модули 1–5 DEMO · ревизия ${log.revision} · ${log.status}`;
  const body = document.createElement('div'); body.className='workflow-log-body';
  if(envelope.result?.client_changes?.length){
    const review=document.createElement('details');review.className='review-required';const title=document.createElement('summary');title.textContent='Изменения клиента · требуется проверка сотрудником по реестрам';review.append(title);
    for(const change of envelope.result.client_changes){const row=document.createElement('p');row.textContent=`${fieldLabels[change.field] || change.field}: ${JSON.stringify(change.old_value)} → ${JSON.stringify(change.new_value)} · ревизия ${change.revision}`;review.append(row);}body.append(review);
  }
  const revisionNote = document.createElement('p'); revisionNote.className='revision-note';
  revisionNote.textContent = lastRevision !== null && log.revision > lastRevision ? `Заявка обновлена: ревизия ${lastRevision} → ${log.revision}. Зависимые результаты пересматриваются модулем 1.` : 'Состояние сохранено на сервере. Проверенные факты и неизвестные сведения показаны отдельно.';
  lastRevision = log.revision;
  const list = document.createElement('dl');
  const add = (label,value) => { const row=document.createElement('div'); const dt=document.createElement('dt'); dt.textContent=label; const dd=document.createElement('dd'); dd.textContent=value; row.append(dt,dd); list.append(row); };
  const unknown='Не указано';
  add('Заявка',log.case_id);
  add('Субъект',`${legalLabels[log.subject.legal_form] || 'Форма не указана'} · ${log.subject.borrower_id || 'Субъект не выбран'}`);
  add('Цель',purposeLabels[log.purpose] || unknown);
  add('Сумма',log.amount_rub === null ? unknown : rubles(log.amount_rub));
  add('Срок',log.term_months === null ? unknown : `${log.term_months} мес.`);
  add('Срочность / дата',log.needed_by || unknown);
  const constraints = Object.entries(log.constraints).filter(([,value])=>value!==null).map(([key,value])=>`${fieldLabels[key]}: ${typeof value==='boolean'?(value?'да':'нет'):value}`);
  add('Известные ограничения и сведения',constraints.join('; ') || 'Не сообщены');
  add('Обязательные уточнения',log.missing_required.map(field=>fieldLabels[field] || field).join(', ') || 'Нет — обязательные поля заполнены');
  add('Все неизвестные поля',log.unknown_fields.map(field=>fieldLabels[field] || field).join(', ') || 'Нет');
  add('Этап',log.completed_stage);
  add('Выполненные операции',log.completed_operations.join(' → '));
  add('Чего ждём',log.waiting_on);
  add('Следующий шаг',log.next_action);
  add('Следующий модуль',log.next_module ? `Модуль ${log.next_module}${log.error_code==='MODULE_NOT_CONFIGURED'?' · пока не подключён':''}` : 'Пока не выбран');
  if(log.error_code) add('Код диагностики',log.error_code);
  const raw=document.createElement('details'); raw.className='raw-log';
  const rawSummary=document.createElement('summary'); rawSummary.textContent='Единый JSON и вызовы инструментов';
  const pre=document.createElement('pre'); pre.textContent=JSON.stringify(envelope,null,2); raw.append(rawSummary,pre);
  body.append(revisionNote);
  if(log.module_2){
    const step=document.createElement('p');step.className='process-next-step';step.textContent=`${log.completed_stage}. ${log.next_module?`Далее: модуль ${log.next_module}`:log.waiting_on}${log.error_code==='MODULE_NOT_CONFIGURED'?' — пока не подключён':''}.`;body.append(step);
    const requestDetails=document.createElement('details');requestDetails.className='candidate-details';const requestTitle=document.createElement('summary');requestTitle.textContent=`Параметры заявки · ${log.amount_rub===null?'сумма не указана':rubles(log.amount_rub)} · ${log.term_months===null?'срок не указан':log.term_months+' мес.'}`;requestDetails.append(requestTitle,list);body.append(requestDetails);
  }else{body.append(list);}
  if(log.data_resolution){
    const resolution=document.createElement('div');resolution.className='revision-note';
    const lookup=document.createElement('p');lookup.textContent=`Проверка профиля в БД: ${log.data_resolution.database_lookup}`;resolution.append(lookup);
    for(const gap of log.data_resolution.gaps){const item=document.createElement('p');item.textContent=`${gap.field} · ${gap.status} · ${gap.resolution}: ${gap.question || gap.reason}`;resolution.append(item);}
    body.append(resolution);
  }
  appendProductLog(body,log);
  if(log.module_3){
    const evidence=document.createElement('pre'); evidence.className='revision-note evidence-log';
    const snapshot=log.module_3;
    evidence.textContent=`Модуль 3 · компания ${snapshot.company_id} · ${snapshot.status}\nSnapshot: ${JSON.stringify(snapshot.snapshot_ids)}\nГотовность автоматической подготовки: ${snapshot.model_readiness}\nБлокировки: ${snapshot.data_quality.blocking_issues.join(', ')}\nНеизвестные признаки: ${snapshot.data_quality.missing_dynamic.join(', ')}\n${log.module_4?'Модуль 4: '+log.module_4.status:'Для оценки нужны явно проверенные входы.'}`;
    body.append(evidence);
    appendQuestionnaire(body,snapshot);
  }
  if(log.module_4){const p=document.createElement('p');p.className='revision-note';const a=log.module_4;p.textContent=`Оценка DEMO: ${a.status} · ${a.kind || 'вероятность недоступна'} · горизонт ${a.horizon_months || '—'} мес. · ${a.probability===null || a.probability===undefined?'Нет оценки':(a.probability*100).toFixed(2)+'%'} · модель ${a.model_id || '—'}. Требуется ручное решение.`;body.append(p);if(a.calculation?.dscr){const c=document.createElement('p');c.textContent=`Иллюстративный расчёт по явным входам: платёж ${a.calculation.monthly_payment_rub} ₽, DSCR ${Number(a.calculation.dscr).toFixed(2)}. Порог решения не применялся; комиссии ${a.calculation.fees_rub===null?'неизвестны':'заданы отдельно'}.`;body.append(c);}}
  if(log.module_5)appendLender(body,log.module_5);
  body.append(raw); details.append(summary,body); messages.append(details);
  messages.scrollTop=details.offsetTop-messages.offsetTop;
  renderCaseControls();
}

function appendQuestionnaire(body,snapshot){
  const fields=snapshot.questionnaire || [];
  if(!fields.length)return;
  const details=document.createElement('details');details.className='candidate-details questionnaire';
  const summary=document.createElement('summary');summary.textContent=`Анкета · не заполнено ${fields.filter(f=>f.status==='MISSING').length} из ${fields.length}`;details.append(summary);
  const form=document.createElement('form');const inputs=[];
  for(const field of fields){
    if(field.editable===false || ['VERIFIED','PRESENT'].includes(field.status)){const p=document.createElement('p');p.textContent=`${field.label}: ${JSON.stringify(field.value)} · ${field.status}${field.editable===false?' · меняется в параметрах заявки':''}`;form.append(p);continue;}
    const label=document.createElement('label');label.textContent=`${field.label} · ${field.product_code}${field.format_rule?' · '+field.format_rule:''}`;
    if(field.review_required){const note=document.createElement('small');note.className='review-required';note.textContent='Изменено клиентом · сотруднику нужно проверить по реестрам';label.append(note);}
    const input=document.createElement(field.data_type==='boolean'?'select':'input');
    if(field.data_type==='boolean'){for(const [value,text] of [['','Не выбрано'],['true','Да'],['false','Нет']]){const option=document.createElement('option');option.value=value;option.textContent=text;input.append(option);}}
    else{input.type=['integer','bigint','smallint','numeric','real','double precision'].includes(field.data_type)?'number':field.data_type==='date'?'date':'text';input.step='any';input.maxLength=12000;}
    const initial=field.value===null?'':String(field.value);input.value=initial;
    label.append(input);form.append(label);inputs.push({field,input,initial});
  }
  const save=document.createElement('button');save.type='submit';save.className='button button-secondary';save.textContent='Сохранить ответы и обновить данные';form.append(save);
  form.addEventListener('submit',async event=>{
    event.preventDefault();save.disabled=true;
    try{
      const answers=inputs.filter(({input,initial})=>input.value!=='' && input.value!==initial).map(({field,input})=>({product_code:field.product_code,field_code:field.field_code,value:field.data_type==='boolean'?input.value==='true':['integer','bigint','smallint','numeric','real','double precision'].includes(field.data_type)?Number(input.value):input.value}));
      if(!answers.length)throw new Error('Заполните хотя бы одно поле.');
      await api('/api/case/fields',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case_id:currentResult.case_id,revision:currentResult.revision,answers})});
      await caseCommand('REFRESH_EVIDENCE',{},'Ответы анкеты сохранены; обновить данные');
    }catch(error){toast(error.message);}finally{save.disabled=false;}
  });
  details.append(form);body.append(details);
}
function appendLender(body,lender){
  const panel=document.createElement('section');panel.className='lender-panel';
  const title=document.createElement('h3');title.textContent=`Рассмотрение DEMO · ${lender.status}`;panel.append(title);
  const text=document.createElement('p');text.textContent=`${lender.lender_case_id}. ${(lender.review_reasons || []).join('; ')}. Реальных банковских операций нет.`;panel.append(text);
  const offer=lender.offer;
  if(offer){
    const p=document.createElement('p');p.textContent=`${rubles(Number(offer.amount_rub))} · ${offer.term_months} мес. · ${(Number(offer.annual_rate_fraction)*100).toFixed(2)}% годовых · комиссии: ${offer.fees_rub.map(v=>rubles(Number(v))).join(', ') || 'нет'} · до ${new Date(offer.expires_at).toLocaleString('ru-RU')}`;panel.append(p);
    const conditions=document.createElement('p');conditions.textContent=`Условия: ${offer.conditions.join('; ') || 'дополнительных условий нет'}`;panel.append(conditions);
    if(offer.assessment_matches_offer===false){const note=document.createElement('p');note.textContent='Условия отличаются от исходного запроса. Оценка модели относится к исходному запросу; изменённые условия утверждены оператором DEMO отдельно.';panel.append(note);}
    if(offer.schedule?.length){const details=document.createElement('details');const label=document.createElement('summary');label.textContent='График платежей по предложению';details.append(label);const table=document.createElement('table');const head=document.createElement('tr');for(const name of ['Месяц','Платёж','Проценты','Основной долг','Остаток']){const th=document.createElement('th');th.textContent=name;head.append(th);}table.append(head);for(const row of offer.schedule){const tr=document.createElement('tr');for(const value of [row.month,row.payment,row.interest,row.principal,row.balance]){const td=document.createElement('td');td.textContent=String(value);tr.append(td);}table.append(tr);}details.append(table);panel.append(details);}
    if(['OFFERED','ACCEPTED'].includes(lender.status)){
      const label=document.createElement('label');const ack=document.createElement('input');ack.type='checkbox';label.append(ack,document.createTextNode(lender.status==='OFFERED'?' Проверил условия; принимаю только предложение DEMO':' Подтверждаю только симуляцию, без перевода денег'));panel.append(label);
      const button=document.createElement('button');button.className='button button-primary';button.textContent=lender.status==='OFFERED'?'Принять предложение DEMO':'Запустить симуляцию исполнения';button.disabled=true;ack.addEventListener('change',()=>{button.disabled=!ack.checked;});button.addEventListener('click',async()=>{button.disabled=true;try{await caseCommand(lender.status==='OFFERED'?'ACCEPT_OFFER':'EXECUTE_DEMO',{offer_id:offer.offer_id,acknowledge_demo:true},button.textContent);}catch(error){toast(error.message);button.disabled=false;}});panel.append(button);
    }
  }
  if(lender.execution){const p=document.createElement('p');p.textContent=`Подтверждена симуляция: ${lender.execution.kind} · ${lender.execution.operation_id}. Реальные деньги не перечислялись.`;panel.append(p);
    if(lender.status==='EXECUTED_DEMO' && offer?.repayment_type==='ANNUITY' && offer.fees_rub.every(fee=>Number(fee)===0)){
      const form=document.createElement('form');const label=document.createElement('label');label.textContent='Сумма имитации платежа по графику, ₽';const amount=document.createElement('input');amount.type='number';amount.min='0.01';amount.step='0.01';amount.required=true;label.append(amount);const button=document.createElement('button');button.className='button button-secondary';button.textContent='Имитировать платёж (без перевода денег)';form.append(label,button);
      let paymentId=null,paymentAmount=null;
      form.addEventListener('submit',async event=>{event.preventDefault();button.disabled=true;try{if(paymentAmount!==amount.value){paymentId=crypto.randomUUID();paymentAmount=amount.value;}const response=await api('/api/case/payment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case_id:currentResult.case_id,operation_id:paymentId,amount_rub:paymentAmount})});currentResult.bank_application=response.bank_application;await refreshAssistant();}catch(error){toast(error.message);button.disabled=false;}});panel.append(form);
    }
    if(lender.servicing){const p=document.createElement('p');p.textContent=`Остаток платежей по графику DEMO: ${lender.servicing.remaining_scheduled_rub} ₽ · ${lender.servicing.closed?'Симуляция погашения завершена':'График обслуживается'}`;panel.append(p);}
  }
  body.append(panel);
}
const eligibilityLabels={MATCH:'Подходит',NO_MATCH:'Не подходит',UNKNOWN:'Неизвестно'};
function appendProductLog(body,log) {
  const title=document.createElement('h3'); title.className='product-log-title'; title.textContent='Подбор продукта'; body.append(title);
  const selection=log.module_2;
  if(!selection){const note=document.createElement('p');note.className='revision-note';note.textContent='Модуль 2 ещё не завершил подбор для этой заявки. Сначала нужны обязательные параметры запроса.';body.append(note);return;}
  const version=document.createElement('p');version.className='revision-note';version.textContent=`${selection.catalog_version} · ${selection.status} · ревизия ${selection.revision}`;body.append(version);
  if(selection.clarification){const note=document.createElement('p');note.className='revision-note';note.textContent=selection.clarification;body.append(note);}
  for(const candidate of selection.candidates){
    const card=document.createElement('article');card.className='product-result';
    const heading=document.createElement('div');heading.className='product-result-heading';
    const name=document.createElement('strong');name.textContent=candidate.name;
    const status=document.createElement('span');status.className=`eligibility ${candidate.eligibility.toLowerCase()}`;status.textContent=eligibilityLabels[candidate.eligibility];heading.append(name,status);card.append(heading);
    if(candidate.database_supported!==null && candidate.database_supported!==undefined){const database=document.createElement('p');database.className='revision-note';database.textContent=candidate.database_supported?`База PostgreSQL · ${candidate.database_product_code} · актуальность условий проверяется отдельно`:'Сбор данных PostgreSQL для этого направления не подключён';card.append(database);}
    const reason=document.createElement('p');reason.textContent=candidate.reasons.join('; ');card.append(reason);
    if(candidate.process!=='CREDIT'){const process=document.createElement('p');process.className='revision-note';process.textContent=`Профильный процесс: ${candidate.process}. Требования обычного кредита его не заменяют.`;card.append(process);}
    const checks=document.createElement('details');checks.className='candidate-details';
    const checksTitle=document.createElement('summary');checksTitle.textContent=`Условия: ${candidate.checks.length} · неизвестно: ${candidate.missing_checks.length}`;checks.append(checksTitle);
    for(const check of candidate.checks){const row=document.createElement('div');row.className='condition-check';const label=document.createElement('strong');label.textContent=check.label;const result=document.createElement('span');result.className=`eligibility ${check.status.toLowerCase()}`;result.textContent=eligibilityLabels[check.status];const text=document.createElement('p');const knownExpected=check.expected&&typeof check.expected==='object'?Object.fromEntries(Object.entries(check.expected).filter(([,value])=>value!==null)):check.expected;text.textContent=`${check.reason} [${check.provenance}]${check.actual!==null?' · Значение: '+JSON.stringify(check.actual):''}${knownExpected&&Object.keys(knownExpected).length?' · Условие: '+JSON.stringify(knownExpected):''}`;row.append(label,result,text);checks.append(row);}card.append(checks);
    const documents=document.createElement('details');documents.className='candidate-details';const docTitle=document.createElement('summary');docTitle.textContent='Документы и ограничения';documents.append(docTitle);
    for(const requirement of candidate.requirements){const item=document.createElement('p');item.textContent=`• ${requirement.label}. Источник: ${requirement.source}. Зачем: ${requirement.purpose}`;documents.append(item);}
    for(const limitation of candidate.limitations){const item=document.createElement('p');item.className='revision-note';item.textContent=limitation;documents.append(item);}card.append(documents);
    const source=document.createElement('p');source.className='product-source';source.textContent=`Источник: ${candidate.source_url} · ${candidate.source_version} · правила ${candidate.rule_version}`;card.append(source);body.append(card);
  }
  if(log.requirements){const note=document.createElement('p');note.className='revision-note';note.textContent=`Для следующего этапа: ${log.requirements.routes.length} маршрутов, ${log.requirements.documents.length} видов документов. ${log.module_3?'Snapshot данных сохранён. Полнота признаков и ограничения — в результате модуля 3.':log.requirements.note}`;body.append(note);}
  if(selection.excluded.length){const excluded=document.createElement('details');excluded.className='candidate-details';const label=document.createElement('summary');label.textContent=`Другие направления: ${selection.excluded.length}`;excluded.append(label);for(const check of selection.excluded){const text=document.createElement('p');text.textContent=`${check.label}: не подходит к текущей потребности. ${check.reason}`;excluded.append(text);}body.append(excluded);}
}
async function api(path,options={}) {
  let response;
  try { response = await fetch(path,{credentials:'same-origin',...options}); }
  catch(error) {
    if(error.name==='AbortError') throw error;
    throw new Error('Нет соединения с API. Запустите python -m personalCab.frontend.server из корня проекта и откройте http://127.0.0.1:5173/.');
  }
  const data = await response.json().catch(()=>null);
  if(response.status===401 && path!=='/api/login')showLogin();
  if(!response.ok || !data){const error=new Error(data?.message || `Сервер недоступен (HTTP ${response.status}). Запустите python -m personalCab.frontend.server из корня проекта.`);error.status=response.status;throw error;}
  return data;
}
async function control(path,arguments_){
  if((failedTurn || pendingCaseCommand) && path!=='/api/consents')throw new Error('Сначала восстановите состояние или повторите неподтверждённое действие.');
  return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:crypto.randomUUID(),arguments:arguments_})});
}
async function caseCommand(command,arguments_={},text=command){
  if(chatBusy || failedTurn)throw new Error('Дождитесь завершения текущего сообщения или повторите неподтверждённый запрос.');
  if(pendingCaseCommand && (pendingCaseCommand.command!==command || JSON.stringify(pendingCaseCommand.arguments)!==JSON.stringify(arguments_)))throw new Error('Повторите прежнее действие или восстановите состояние перед новой командой.');
  const turn=pendingCaseCommand || {message_id:crypto.randomUUID(),text,command,arguments:arguments_};
  chatBusy=true;syncSend();renderCaseControls();
  try{
    const envelope=await api('/api/case/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(turn)});
    pendingCaseCommand=null;
    $('.chat-welcome')?.remove();addMessage(envelope.result.message,'assistant');appendWorkflowLog(envelope);
    try{await loadApplications();}catch(error){toast(error.message);}
    return envelope;
  }catch(error){if(!error.status || error.status>=500 || error.status===409)pendingCaseCommand=turn;throw error;
  }finally{chatBusy=false;syncSend();renderCaseControls();}
}
function renderCaseControls(){
  const panel=$('#case-controls-body');if(!panel)return;panel.replaceChildren();
  if(!currentContext){panel.textContent='Восстановите соединение с сервером.';return;}
  const waitingForConsent=currentResult?.next_action==='PROVIDE_CONSENT';
  const hintKey=waitingForConsent?`${currentResult.case_id}:${currentResult.revision}`:null;
  if(hintKey && hintKey!==shownConsentHint){$('#case-controls').open=true;shownConsentHint=hintKey;}
  const steps=document.createElement('section');steps.className='consent-steps';steps.setAttribute('aria-label','Получение сведений о бизнесе');
  const heading=document.createElement('strong');heading.textContent=currentContext.consents.EVIDENCE_COLLECTION?'Разрешение получено — можно обновить анкету':'Чтобы загрузить сведения о вашем бизнесе';steps.append(heading);
  const explanation=document.createElement('p');explanation.textContent='Сначала дайте разрешение, затем загрузите сведения в анкету. Без разрешения они не запрашиваются.';steps.append(explanation);panel.append(steps);
  const company=document.createElement('label');company.textContent='Выбранная компания DEMO';const select=document.createElement('select');
  for(const item of currentContext.companies){const option=document.createElement('option');option.value=item.company_id;option.textContent=`${item.name} · ${item.company_id}`;option.selected=item.company_id===currentContext.company_id;select.append(option);}
  select.disabled=chatBusy || Boolean(failedTurn) || Boolean(pendingCaseCommand) || currentContext.companies.length<2;select.addEventListener('change',async()=>{select.disabled=true;try{await control('/api/context',{company_id:Number(select.value)});await refreshAssistant();}catch(error){toast(error.message);}});company.append(select);panel.append(company);
  const otherConsents=document.createElement('details');const otherTitle=document.createElement('summary');otherTitle.textContent='Дополнительные согласия для следующих этапов';otherConsents.append(otherTitle);
  const scopeLabels={EVIDENCE_COLLECTION:'1. Разрешаю получить сведения о моём бизнесе',CREDIT_ASSESSMENT:'Оценка синтетической моделью',BANK_STATUS:'Получение статуса рассмотрения DEMO',APPLICATION_SUBMISSION:'Передача на ручное рассмотрение и принятие условий DEMO',DEMO_EXECUTION:'Симуляция исполнения'};
  for(const [scope,title] of Object.entries(scopeLabels)){
    const label=document.createElement('label');const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=Boolean(currentContext.consents[scope]);checkbox.disabled=chatBusy || !currentContext.company_id;
    checkbox.id=`consent-${scope.toLowerCase()}`;
    checkbox.addEventListener('change',async()=>{checkbox.disabled=true;try{await control('/api/consents',{scope,granted:checkbox.checked});await refreshAssistant();}catch(error){toast(error.message);checkbox.disabled=false;}});label.append(checkbox,document.createTextNode(` ${title}`));(scope==='EVIDENCE_COLLECTION'?steps:otherConsents).append(label);
  }
  const notice=document.createElement('small');notice.textContent='Разрешение действует 1 час. Чтобы отозвать его, снимите галочку. Здесь используются демонстрационные данные.';steps.append(notice);
  if(pendingCaseCommand){const retry=document.createElement('button');retry.className='button button-secondary';retry.textContent='Повторить неподтверждённое действие';retry.disabled=chatBusy;retry.addEventListener('click',async()=>{const saved=pendingCaseCommand;try{await caseCommand(saved.command,saved.arguments,saved.text);}catch(error){toast(error.message);}});panel.append(retry);}
  for(const [command,title,disabled] of [['REFRESH_EVIDENCE','Обновить данные и анкету',!currentResult],['ASSESS','Запустить оценку CatBoost',!currentResult?.data_context],['SUBMIT','Передать оператору DEMO',!currentResult?.assessment],['POLL_STATUS','Проверить рассмотрение DEMO',!currentResult?.bank_application]]){
    const button=document.createElement('button');button.type='button';button.className=command==='REFRESH_EVIDENCE'?'button button-primary':'button button-secondary';button.textContent=title;button.disabled=chatBusy || Boolean(disabled) || ['CANCELLED','COMPLETED'].includes(currentResult?.status) || (command==='REFRESH_EVIDENCE' && !currentContext.consents.EVIDENCE_COLLECTION);button.addEventListener('click',async()=>{try{await caseCommand(command,['REFRESH_EVIDENCE','POLL_STATUS'].includes(command)?{}:{product_code:$('#assessment-product')?.value || 'R01'},title);}catch(error){toast(error.message);}});
    if(command==='REFRESH_EVIDENCE'){const caption=document.createElement('p');caption.textContent='2. Загрузите сведения в анкету';steps.append(caption,button);button.id='refresh-evidence-button';}else panel.append(button);
  }
  panel.append(otherConsents);
  if(currentResult?.data_context){const label=document.createElement('label');label.textContent='Маршрут оценки и рассмотрения';const choice=document.createElement('select');choice.id='assessment-product';const codes=Object.keys(currentResult.data_context.application_ids);if(!codes.includes(selectedProductCode))selectedProductCode=codes[0];for(const code of codes){const option=document.createElement('option');option.value=code;option.textContent=code;option.selected=code===selectedProductCode;choice.append(option);}choice.disabled=chatBusy;choice.addEventListener('change',()=>{selectedProductCode=choice.value;});label.append(choice);panel.append(label);}
  $('#start-new-case').disabled=chatBusy || Boolean(failedTurn) || Boolean(pendingCaseCommand) || (Boolean(currentResult) && !['CANCELLED','COMPLETED'].includes(currentResult.status));
  const active=currentContext.companies.find(item=>item.company_id===currentContext.company_id);
  if(active){$('.company-card h2').textContent=active.name;$('.company-card > p').textContent=`${active.entity_type} · PostgreSQL ${active.company_id}`;$('.company-card dl').hidden=true;$('.company-card .demo-note').textContent='Выбранный синтетический субъект. Сведения доступны только в пределах разрешений DEMO.';$('.company-switch > span:nth-child(2)').firstChild.textContent=active.name;}
}
async function uploadFile(file){
  if(!currentResult)await caseCommand('UPDATE_REQUEST',{patch:{}},'Подготовить заявку для документов');
  const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Не удалось прочитать файл'));reader.readAsDataURL(file);});
  const response=await api('/api/documents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case_id:currentResult.case_id,filename:file.name,content_base64:encoded})});
  documents=response.documents;renderDocuments();
}
function requestStatus(text) { $('#chat-request-status').hidden=!text; $('#chat-request-status').textContent=text; }
async function refreshAssistant() {
  if(chatBusy && chatConnected) return;
  chatBusy=true; syncSend(); requestStatus('Восстанавливаем состояние заявки…');
  try {
    const state=await api('/api/chat/state');
    chatConnected=true;
    currentContext=state.context;currentResult=state.latest?.result || null;
    if(currentContext.client){
      const name=currentContext.client.full_name;
      $('.user > span:nth-child(2)').firstChild.textContent=name;
      $('#overview-title').textContent=`Добрый день, ${name.split(' ')[1] || name}`;
      if(!$('#logout-button')){const logout=document.createElement('button');logout.id='logout-button';logout.className='text-button';logout.textContent='Выйти';logout.addEventListener('click',async()=>{await control('/api/logout',{});location.reload();});$('.topbar-actions').append(logout);}
    }
    if(pendingCaseCommand && state.latest?.message_id===pendingCaseCommand.message_id)pendingCaseCommand=null;
    if(failedTurn && state.latest?.message_id!==failedTurn.message_id) {
      requestStatus('Последнее сообщение пока не подтверждено сервером. Используйте «Повторить запрос» с тем же ID.');
    } else {
      failedTurn=null; lastRevision=null;
      messages.replaceChildren();
      if(!state.history.length) messages.append(initialWelcome.cloneNode(true));
      else {
        state.history.forEach(item=>addMessage(item.content,item.role==='user'?'user':'assistant'));
        if(state.latest) appendWorkflowLog(state.latest);
      }
      requestStatus('');
    }
    const health=await api('/api/health');
    const label=$('#assistant-connection span');
    label.textContent=health.status==='ready'?`${health.modules.includes(5)?'Модули 1–5 DEMO':'Модули 1–2 legacy'} · gpt-oss:20b`:health.status==='model_missing'?'Модель gpt-oss:20b не установлена':health.status==='storage_unavailable'?'Хранилище недоступно':'Ollama недоступен';
    $('#assistant-connection').dataset.state=health.status;
    await loadApplications();
    if(currentResult){const saved=await api('/api/documents');documents=saved.documents;}else{documents=[];}renderDocuments();
    if(pendingCaseCommand)requestStatus('Действие пока не подтверждено. Повторите ту же команду; идентификатор будет сохранён.');
  } catch(error) {
    if(!chatConnected) $('#assistant-connection span').textContent='Нет соединения с сервером';
    requestStatus(error.message);
  } finally { chatBusy=false; syncSend();renderCaseControls(); }
}
async function sendTurn(turn,attachment=null,retry=false) {
  if(chatBusy) return;
  chatBusy=true; syncSend();
  if(!retry) { $('.chat-welcome')?.remove(); addMessage(turn.text,'user',attachment); }
  const started=Date.now();
  requestStatus('Модель разбирает сообщение…');
  const ticker=setInterval(()=>requestStatus(`Модель разбирает сообщение… ${Math.floor((Date.now()-started)/1000)} с`),1000);
  const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),300000);
  try {
    const envelope=await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(turn),signal:controller.signal});
    failedTurn=null;
    messages.querySelectorAll('.retry-turn').forEach(button=>button.remove());
    addMessage(envelope.result.message,'assistant'); appendWorkflowLog(envelope);
    try{await loadApplications();}catch(error){toast(error.message);}
    if(attachment){try{await uploadFile(attachment);toast('Файл сохранён; обновите данные для включения в снимок.');}catch(error){const row=addMessage('Сообщение сохранено. Файл не загружен: '+error.message,'system');const retry=document.createElement('button');retry.className='button button-secondary';retry.textContent='Повторить загрузку файла';retry.addEventListener('click',async()=>{retry.disabled=true;try{await uploadFile(attachment);retry.remove();toast('Файл сохранён');}catch(error){toast(error.message);retry.disabled=false;}});row.append(retry);}}
    requestStatus('');
  } catch(error) {
    failedTurn=turn;
    const row=addMessage(`${error.name==='AbortError'?'Истекло время ожидания. Обработка на сервере могла завершиться.':error.message} Повтор использует прежний message_id и не создаёт дубль.`, 'system');
    messages.querySelectorAll('.retry-turn').forEach(button=>button.remove());
    const retryButton=document.createElement('button'); retryButton.className='button button-secondary retry-turn'; retryButton.textContent='Повторить запрос';
    retryButton.addEventListener('click',()=>sendTurn(turn,null,true)); row.append(retryButton);
    requestStatus('Запрос не подтверждён. Повторите его или обновите состояние.');
  } finally { clearInterval(ticker); clearTimeout(timeout); chatBusy=false; syncSend();renderCaseControls(); }
}
$('#chat-form').addEventListener('submit',event=>{
  event.preventDefault();
  const text=$('#chat-input').value.trim();
  if(!text || chatBusy || !chatConnected || failedTurn || pendingCaseCommand) return;
  const turn={message_id:crypto.randomUUID(),text};
  const attachment=pendingAttachment;
  $('#chat-input').value=''; pendingAttachment=null; renderAttachment();
  sendTurn(turn,attachment);
});
$('#chat-input').addEventListener('input',syncSend);
$('#chat-input').addEventListener('keydown',event=>{
  if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('#chat-form').requestSubmit();}
});
messages.addEventListener('click',event=>{
  const suggestion=event.target.closest('[data-prompt]');
  if(suggestion&&!chatBusy){$('#chat-input').value=suggestion.dataset.prompt;syncSend();$('#chat-input').focus();}
});
$('#new-chat').addEventListener('click',refreshAssistant);
$('#start-new-case').addEventListener('click',async()=>{try{await control('/api/session/new',{});await refreshAssistant();}catch(error){toast(error.message);}});
function renderAttachment() {
  const container = $('#chat-attachment');
  container.replaceChildren();
  container.hidden = !pendingAttachment;
  if (!pendingAttachment) return;
  const label = document.createElement('span'); label.textContent = pendingAttachment.name;
  const remove = document.createElement('button'); remove.type='button'; remove.textContent='×'; remove.setAttribute('aria-label','Убрать вложение');
  remove.addEventListener('click', () => { pendingAttachment = null; renderAttachment(); syncSend(); });
  container.append(label,remove);
}
function validFile(file) {
  if (!/\.(pdf|csv|xlsx?|png|jpe?g)$/i.test(file.name)) { toast('Выберите PDF, Excel, CSV или изображение PNG/JPEG.'); return false; }
  if (file.size > 20 * 1024 * 1024) { toast(`Файл «${file.name}» больше 20 МБ.`); return false; }
  return true;
}
$('#attach-chat-file').addEventListener('click', () => $('#chat-file-input').click());
$('#chat-file-input').addEventListener('change', event => {
  const file = event.target.files[0];
  if (file && validFile(file)) { pendingAttachment = file; renderAttachment(); syncSend(); }
  event.target.value = '';
});
function renderDocuments() {
  const list = $('#documents-list'); list.replaceChildren();
  documents.forEach(file => {
    const row = document.createElement('article'); row.className='document-row';
    const icon = document.createElement('span'); icon.className='product-icon'; icon.innerHTML='<img src="front_assets/document.svg" alt="">';
    const detail = document.createElement('div');
    const name = document.createElement('strong'); name.textContent=file.filename;
    const size = document.createElement('small'); size.textContent=`${file.document_id} · ${file.status} · сохранён на сервере, требует проверки`;
    detail.append(name,size);
    row.append(icon,detail); list.append(row);
  });
  $('.notification-dot').hidden=!documents.length;
}
['#add-document','#select-documents'].forEach(selector => $(selector).addEventListener('click', () => $('#document-input').click()));
$('#document-input').addEventListener('change',async event => {
  const files=[...event.target.files];event.target.value='';
  try{for (const file of files) if (validFile(file))await uploadFile(file);toast('Документы сохранены. Обновите данные заявки, чтобы включить их в снимок.');}catch(error){toast(error.message);}
});
function renderChart(period) {
  const monthly = [{label:'1–5 окт',income:220,expense:150},{label:'6–10 окт',income:300,expense:200},{label:'11–15 окт',income:260,expense:180},{label:'16–20 окт',income:350,expense:230},{label:'21–25 окт',income:280,expense:190},{label:'26–31 окт',income:440,expense:290}];
  const weekly = [{label:'Пн',income:40,expense:25},{label:'Вт',income:68,expense:41},{label:'Ср',income:53,expense:30},{label:'Чт',income:89,expense:55},{label:'Пт',income:65,expense:34},{label:'Сб',income:48,expense:20},{label:'Вс',income:32,expense:21}];
  const data = period === 'week' ? weekly : monthly;
  const maximum = Math.max(...data.flatMap(item => [item.income,item.expense]));
  $('#bar-chart').innerHTML = data.map(item => `<div class="bar-group" aria-label="${item.label}: поступления ${item.income} тыс. рублей, расходы ${item.expense} тыс. рублей"><span class="bar" style="height:${item.income/maximum*100}%"></span><span class="bar expense" style="height:${item.expense/maximum*100}%"></span><span class="bar-label">${item.label}</span></div>`).join('');
  $('.chart-total').textContent='+' + rubles(data.reduce((total,item) => total+item.income-item.expense,0)*1000);
}
$('#chart-period').addEventListener('change',event => renderChart(event.target.value));
const menu = $('.mobile-menu');
const mobileNavigation = matchMedia('(max-width: 700px)');
function closeMenu() { $('#sidebar').classList.remove('menu-open'); $('#sidebar').inert = mobileNavigation.matches; menu.setAttribute('aria-expanded','false'); menu.setAttribute('aria-label','Открыть меню'); }
mobileNavigation.addEventListener('change', closeMenu);
closeMenu();
menu.addEventListener('click', () => {
  const open = !$('#sidebar').classList.contains('menu-open');
  $('#sidebar').classList.toggle('menu-open',open);
  $('#sidebar').inert = !open && mobileNavigation.matches;
  menu.setAttribute('aria-expanded',String(open)); menu.setAttribute('aria-label',open?'Закрыть меню':'Открыть меню');
});
document.addEventListener('click', event => { if (!event.target.closest('#sidebar') && !event.target.closest('.mobile-menu')) closeMenu(); });
document.addEventListener('keydown',event => { if (event.key==='Escape') { closeMenu(); if(chat.open && !$('#application-dialog').open) closeChat(); } });
function showLogin(){const dialog=$('#login-dialog');if(!dialog.open)dialog.showModal();chatConnected=false;syncSend();}
$('#login-dialog').addEventListener('cancel',event=>event.preventDefault());
$('#login-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const button=form.querySelector('button');button.disabled=true;
  try{await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:form.elements.login.value,password:form.elements.password.value})});form.reset();$('#login-error').textContent='';$('#login-dialog').close();await refreshAssistant();}
  catch(error){$('#login-error').textContent=error.message;}finally{button.disabled=false;}
});
renderApplications(); renderChart('month'); syncSend();
refreshAssistant();
