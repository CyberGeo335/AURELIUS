import { Check, Clock3, ArrowRight } from 'lucide-react';
import { Card } from './primitives';
import { datetime } from '../../domain/finance';
import { clientStatus } from '../../domain/clientStatus';
import type { Application } from '../../domain/types';
export function ClientJourney({ app }: { app: Application }) {
  const status = clientStatus(app);
  const events = [...app.history]
    .reverse()
    .flatMap((event) => {
      const t = event.text;
      const label = t.startsWith('Заявка отправлена')
        ? 'Заявка принята'
        : t.startsWith('Получены дополнительные данные')
          ? 'Ваш ответ получен — проверка продолжена'
          : t.startsWith('Запросили') || t.startsWith('Запрошены данные')
            ? 'Нужно уточнение по заявке'
            : t.startsWith('Подготовили предложение') || t.startsWith('Встречное предложение')
              ? 'Для вас готово предложение'
              : t.startsWith('Предложение принято')
                ? 'Вы приняли предложение'
                : t.startsWith('Договор подписан')
                  ? 'Договор подписан на демо-стенде'
                  : t.startsWith('Деньги на счёте')
                    ? 'Демонстрационная выдача завершена'
                    : t.startsWith('Демо-отказ') || t.startsWith('Отказ:')
                      ? 'По заявке принято решение'
                      : t.startsWith('Передано специалисту')
                        ? 'Заявку рассматривает специалист'
                        : undefined;
      return label ? [{ id: event.id, label, at: event.at }] : [];
    })
    .slice(-5);
  return (
    <Card id="history" className="client-journey">
      <h2>Ваша заявка</h2>
      <div className="client-next">
        <Clock3 aria-hidden size={22} />
        <div>
          <strong>{status.happening}</strong>
          <p className="muted">{status.next}</p>
        </div>
      </div>
      {events.length > 0 && (
        <ol className="client-timeline" aria-label="История заявки">
          {events.map((event, i) => (
            <li key={event.id}>
              <span>
                {i === events.length - 1 ? (
                  <ArrowRight aria-hidden size={16} />
                ) : (
                  <Check aria-hidden size={16} />
                )}
              </span>
              <div>
                <strong>{event.label}</strong>
                <time>{datetime(event.at)}</time>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
