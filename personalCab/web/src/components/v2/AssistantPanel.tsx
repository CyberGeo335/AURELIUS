import { useEffect, useState, useRef } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { Textarea } from '../ui/textarea';
import { Action, ErrorState } from './primitives';
import { HttpChatApi } from '../../api/HttpChatApi';
import { useAction, useSession } from '../../app/context';
import { money } from '../../domain/finance';
const chat = new HttpChatApi();
export function AssistantPanel({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { session } = useSession();
  const action = useAction();
  const [text, setText] = useState('');
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [status, setStatus] = useState('Проверяем подключение…');
  const [facts, setFacts] = useState<Record<string, unknown>>({});
  const pending = useRef<{ id: string; text: string } | null>(null);
  const mode = import.meta.env.VITE_API_MODE ?? 'mock';
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    if (mode !== 'http') return;
    void Promise.all([chat.health(), chat.state()])
      .then(([health, state]) => {
        if (cancelled) return;
        setStatus(
          health.status === 'ready'
            ? 'Помощник подключён'
            : 'Ollama или модель недоступны. Основная анкета работает.',
        );
        setMessages(state.history.map((m) => ({ role: m.role, text: m.content ?? m.text ?? '' })));
        setFacts(state.latest?.result.request ?? {});
      })
      .catch((e) => {
        if (!cancelled) setStatus(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [open, mode]);
  const send = () =>
    action.run(async () => {
      const message = pending.current ?? { id: crypto.randomUUID(), text: text.trim() };
      pending.current = message;
      const response = await chat.send(message.text, message.id);
      setMessages((m) => [
        ...m,
        { role: 'user', text: message.text },
        {
          role: 'assistant',
          text: response.result.message ?? 'Ответ получен. Проверьте сведения в анкете.',
        },
      ]);
      pending.current = null;
      setFacts(response.result.request ?? {});
      setText('');
    });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} modal={false}>
      <DialogContent className="assistant-drawer">
        <DialogHeader>
          <DialogTitle>Помощник</DialogTitle>
          <DialogDescription>
            Извлечённые из диалога значения нужно подтвердить в форме. Согласия оформляются
            отдельно.
          </DialogDescription>
        </DialogHeader>
        {mode === 'mock' ? (
          <div className="inset">
            <h3>Помощник сейчас не подключён</h3>
            <p>Продолжите заявку через форму: все шаги и подсказки доступны без помощника.</p>
          </div>
        ) : (
          <>
            <p role="status" className="small muted">
              {status}
            </p>
            <p className="small muted">
              Это отдельный демонстрационный диалог. Чтобы изменить заявку{' '}
              {session?.profile === 'zerno' ? 'ООО «Зерно Опт»' : 'ИП Карпова'}, подтвердите
              сведения в её анкете.
            </p>
            <div className="chat-messages" aria-live="polite">
              {messages.length ? (
                messages.map((m, i) => (
                  <div key={i} className={`bubble ${m.role === 'user' ? 'user' : 'assistant'}`}>
                    {m.text}
                  </div>
                ))
              ) : (
                <p className="muted">Расскажите, для чего бизнесу нужны деньги.</p>
              )}
            </div>
            {Object.entries(facts).some(
              ([key, value]) =>
                ['amount_rub', 'term_months', 'legal_form', 'purpose'].includes(key) &&
                value != null,
            ) && (
              <details>
                <summary>Извлечено из диалога</summary>
                <dl className="details">
                  {Object.entries(facts)
                    .filter(
                      ([key, value]) =>
                        ['amount_rub', 'term_months', 'legal_form', 'purpose'].includes(key) &&
                        value != null,
                    )
                    .map(([key, value]) => (
                      <div className="contents" key={key}>
                        <dt>
                          {
                            {
                              amount_rub: 'Сумма',
                              term_months: 'Срок, мес.',
                              legal_form: 'Форма бизнеса',
                              purpose: 'Цель',
                            }[key]
                          }
                        </dt>
                        <dd>
                          {key === 'amount_rub' && typeof value === 'number'
                            ? money(value)
                            : String(value)}
                          <span className="small muted block">Подтвердите в анкете</span>
                        </dd>
                      </div>
                    ))}
                </dl>
              </details>
            )}
            <ErrorState message={action.error} />
            <label className="form-field">
              Сообщение
              <Textarea
                maxLength={12000}
                value={text}
                disabled={action.busy || !!pending.current}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <Action disabled={action.busy || (!text.trim() && !pending.current)} onClick={send}>
              {action.busy
                ? 'Помощник отвечает…'
                : pending.current
                  ? 'Повторить сообщение'
                  : 'Отправить'}
            </Action>
            {pending.current && !action.busy && (
              <Action
                tone="ghost"
                onClick={() => {
                  pending.current = null;
                  action.setError('');
                  setText('');
                }}
              >
                Написать другое сообщение
              </Action>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
