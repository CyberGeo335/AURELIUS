'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const storageKey = 'aurelius.dashboard.drafts.v1';
const defaultDraft = {id:'AUR-001',name:'Кредит на развитие бизнеса',amount:3000000,term:24,purpose:'Развитие бизнеса'};
let drafts = [{...defaultDraft}];
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
try {
  const saved = JSON.parse(localStorage.getItem(storageKey));
  if (Array.isArray(saved) && saved.length && saved.every(item => item && typeof item.id === 'string' && typeof item.name === 'string' && typeof item.purpose === 'string' && Number.isFinite(item.amount) && item.amount >= 100000 && item.amount <= 150000000 && [12,24,36,60].includes(item.term))) drafts = saved;
} catch { /* Storage may be unavailable; the in-memory demo remains usable. */ }
function persistDrafts() {
  try { localStorage.setItem(storageKey, JSON.stringify(drafts)); return true; }
  catch { toast('Черновик сохранён в памяти страницы. Хранилище браузера недоступно.'); return false; }
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
  $('#overview-application-number').textContent = `Заявка № ${latest.id}`;
  $('.application-top h3').textContent = latest.name;
  $('#overview-amount').textContent = rubles(latest.amount);
  $('#overview-term').textContent = `${latest.term} ${latest.term === 24 ? 'месяца' : 'месяцев'}`;
  $('#applications-list').innerHTML = drafts.map(item => `<article class="application-card application-list-item"><div class="application-top"><div class="product-icon"><img src="front_assets/money.svg" alt=""></div><div><h3>${escapeHtml(item.name)}</h3><p>Заявка № ${escapeHtml(item.id)}</p></div><span class="status">Черновик</span></div><div class="application-data"><div><small>Сумма кредита</small><strong>${rubles(item.amount)}</strong></div><div><small>Срок</small><strong>${item.term} ${item.term === 24 ? 'месяца' : 'месяцев'}</strong></div><button class="button button-secondary" data-edit-id="${escapeHtml(item.id)}">Продолжить →</button></div><p class="application-purpose">${escapeHtml(item.purpose)} · Не отправлена в банк</p></article>`).join('');
}
function openApplication(draft) {
  editingId = draft?.id ?? null;
  $('#application-name').value = draft?.name ?? '';
  $('#application-amount').value = draft?.amount ?? 3000000;
  $('#application-term').value = String(draft?.term ?? 24);
  $('#application-purpose').value = draft?.purpose ?? 'Развитие бизнеса';
  $('#application-dialog').showModal();
}
$$('[data-new-application]').forEach(button => button.addEventListener('click', () => openApplication()));
$('[data-edit-application]').addEventListener('click', () => openApplication(drafts[0]));
$('#applications-list').addEventListener('click', event => {
  const button = event.target.closest('[data-edit-id]');
  if (button) openApplication(drafts.find(item => item.id === button.dataset.editId));
});
$('#application-form').addEventListener('submit', event => {
  event.preventDefault();
  const name = $('#application-name').value.trim();
  if (!name) { $('#application-name').setCustomValidity('Введите название проекта'); $('#application-name').reportValidity(); return; }
  const draft = {id:editingId ?? `AUR-${Date.now().toString(36).toUpperCase()}`,name,amount:Number($('#application-amount').value),term:Number($('#application-term').value),purpose:$('#application-purpose').value};
  if (editingId) drafts = drafts.map(item => item.id === editingId ? draft : item); else drafts.unshift(draft);
  const persisted = persistDrafts();
  renderApplications();
  $('#application-dialog').close();
  if (persisted) toast('Черновик сохранён в браузере. Заявка не отправлена в банк.');
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
  $('.send-button').disabled = chatBusy || !chatConnected || Boolean(failedTurn) || !$('#chat-input').value.trim();
  $('#new-chat').disabled = chatBusy;
  $('#attach-chat-file').disabled = chatBusy;
  $('#chat-input').readOnly = chatBusy;
}
function addMessage(text, kind, attachment) {
  const message = document.createElement('div');
  message.className = `message ${kind}-message`;
  const label = document.createElement('small');
  label.textContent = kind === 'user' ? 'Вы' : kind === 'assistant' ? 'Бизнес-ассистент' : 'Системное сообщение';
  const content = document.createElement('p'); content.textContent = text;
  message.append(label,content);
  if (attachment) { const file = document.createElement('p'); file.className = 'attached'; file.textContent = `Файл: ${attachment.name} · остаётся локально, не анализируется`; message.append(file); }
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}
const fieldLabels = {borrower_id:'субъект',legal_form:'форма бизнеса',purpose:'цель',amount_rub:'сумма',term_months:'срок',needed_by:'дата потребности',repayment_source:'источник возврата',recurring:'повторяемость потребности',known_obligations:'обязательства',seasonality:'сезонность',collateral:'обеспечение',financing_need:'характер потребности',business_age_months:'возраст бизнеса, мес.',monthly_revenue_rub:'месячный оборот, ₽',operating_cycle_days:'оборотный цикл, дней',has_collateral:'наличие обеспечения'};
const purposeLabels = {INVENTORY:'Закупка товара',WORKING_CAPITAL:'Оборотные средства',INVESTMENT:'Инвестиции',REAL_ESTATE:'Недвижимость',VEHICLE:'Транспорт',REFINANCING:'Рефинансирование',GUARANTEE:'Гарантия',OTHER:'Другая цель'};
const legalLabels = {IP:'ИП',OOO:'ООО',AO:'АО',OTHER:'Другая форма'};
function appendWorkflowLog(envelope) {
  const log = envelope.workflow_log;
  messages.querySelectorAll('.workflow-log').forEach(item=>item.remove());
  const details = document.createElement('details'); details.className='workflow-log'; details.open=true;
  const summary = document.createElement('summary'); summary.textContent=`Общий лог · модули 1–2 · ревизия ${log.revision} · ${log.status}`;
  const body = document.createElement('div'); body.className='workflow-log-body';
  const revisionNote = document.createElement('p'); revisionNote.className='revision-note';
  revisionNote.textContent = lastRevision !== null && log.revision > lastRevision ? `Заявка обновлена: ревизия ${lastRevision} → ${log.revision}. Зависимые результаты пересматриваются модулем 1.` : 'Состояние сохранено на сервере · SQLite. Сведения клиента ещё не проверены.';
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
    const step=document.createElement('p');step.className='process-next-step';step.textContent=`${log.completed_stage}. ${log.next_module?`Далее: модуль ${log.next_module}`:'Ждём уточнения'}${log.error_code==='MODULE_NOT_CONFIGURED'?' — пока не подключён':''}.`;body.append(step);
    const requestDetails=document.createElement('details');requestDetails.className='candidate-details';const requestTitle=document.createElement('summary');requestTitle.textContent=`Параметры заявки · ${log.amount_rub===null?'сумма не указана':rubles(log.amount_rub)} · ${log.term_months===null?'срок не указан':log.term_months+' мес.'}`;requestDetails.append(requestTitle,list);body.append(requestDetails);
  }else{body.append(list);}
  appendProductLog(body,log);
  body.append(raw); details.append(summary,body); messages.append(details);
  messages.scrollTop=details.offsetTop-messages.offsetTop;
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
  if(log.requirements){const note=document.createElement('p');note.className='revision-note';note.textContent=`Для следующего этапа: ${log.requirements.routes.length} маршрутов, ${log.requirements.documents.length} видов документов. ${log.requirements.note}`;body.append(note);}
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
  if(!response.ok || !data) throw new Error(data?.message || `Сервер недоступен (HTTP ${response.status}). Запустите python -m personalCab.frontend.server из корня проекта.`);
  return data;
}
function requestStatus(text) { $('#chat-request-status').hidden=!text; $('#chat-request-status').textContent=text; }
async function refreshAssistant() {
  if(chatBusy && chatConnected) return;
  chatBusy=true; syncSend(); requestStatus('Восстанавливаем состояние заявки…');
  try {
    const state=await api('/api/chat/state');
    chatConnected=true;
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
    label.textContent=health.status==='ready'?'Модули 1–2 · gpt-oss:20b':health.status==='model_missing'?'Модель gpt-oss:20b не установлена':'Ollama недоступен';
    $('#assistant-connection').dataset.state=health.status;
  } catch(error) {
    if(!chatConnected) $('#assistant-connection span').textContent='Нет соединения с сервером';
    requestStatus(error.message);
  } finally { chatBusy=false; syncSend(); }
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
    requestStatus('');
  } catch(error) {
    failedTurn=turn;
    const row=addMessage(`${error.name==='AbortError'?'Истекло время ожидания. Обработка на сервере могла завершиться.':error.message} Повтор использует прежний message_id и не создаёт дубль.`, 'system');
    messages.querySelectorAll('.retry-turn').forEach(button=>button.remove());
    const retryButton=document.createElement('button'); retryButton.className='button button-secondary retry-turn'; retryButton.textContent='Повторить запрос';
    retryButton.addEventListener('click',()=>sendTurn(turn,null,true)); row.append(retryButton);
    requestStatus('Запрос не подтверждён. Повторите его или обновите состояние.');
  } finally { clearInterval(ticker); clearTimeout(timeout); chatBusy=false; syncSend(); }
}
$('#chat-form').addEventListener('submit',event=>{
  event.preventDefault();
  const text=$('#chat-input').value.trim();
  if(!text || chatBusy || !chatConnected || failedTurn) return;
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
  documents.forEach((file,index) => {
    const row = document.createElement('article'); row.className='document-row';
    const icon = document.createElement('span'); icon.className='product-icon'; icon.innerHTML='<img src="front_assets/document.svg" alt="">';
    const detail = document.createElement('div');
    const name = document.createElement('strong'); name.textContent=file.name;
    const size = document.createElement('small'); size.textContent=`${(file.size/1024).toFixed(1)} КБ · Локально, не отправлен`;
    detail.append(name,size);
    const remove = document.createElement('button'); remove.className='icon-button'; remove.textContent='×'; remove.setAttribute('aria-label',`Убрать ${file.name} из списка`);
    remove.addEventListener('click', () => { documents.splice(index,1); renderDocuments(); });
    row.append(icon,detail,remove); list.append(row);
  });
  $('.notification-dot').hidden=!documents.length;
}
['#add-document','#select-documents'].forEach(selector => $(selector).addEventListener('click', () => $('#document-input').click()));
$('#document-input').addEventListener('change',event => {
  for (const file of event.target.files) if (validFile(file) && !documents.some(existing => existing.name===file.name && existing.size===file.size && existing.lastModified===file.lastModified)) documents.push(file);
  renderDocuments(); event.target.value='';
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
renderApplications(); renderChart('month'); syncSend();
refreshAssistant();
