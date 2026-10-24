export interface ChatResult {
  result: {
    reply?: string;
    message?: string;
    assistant_message?: string;
    error_code?: string;
    request?: Record<string, unknown>;
  };
  workflow_log?: Record<string, unknown>;
}
export interface ChatState {
  history: { role: string; content?: string; text?: string }[];
  latest: ChatResult | null;
}
export class HttpChatApi {
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(path, {
        ...init,
        credentials: 'include',
        signal: AbortSignal.timeout(90000),
      });
    } catch {
      throw new Error(
        'Помощник недоступен. Проверьте Python-сервер и Ollama. Заявку можно заполнить через форму.',
      );
    }
    if (response.status === 428 && init?.method === 'POST') return this.retrySession<T>(path, init);
    return this.parse<T>(response);
  }
  private async retrySession<T>(path: string, init: RequestInit) {
    const response = await fetch(path, {
      ...init,
      credentials: 'include',
      signal: AbortSignal.timeout(90000),
    });
    return this.parse<T>(response);
  }
  private async parse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const errors: Record<number, string> = {
        400: 'Сообщение не принято. Проверьте текст.',
        409: 'Предыдущий запрос ещё обрабатывается. Повторите это сообщение позже.',
        428: 'Не удалось создать сессию. Разрешите cookies и повторите.',
        503: 'Хранилище помощника временно недоступно. Повторите сообщение позже.',
      };
      throw new Error(
        errors[response.status] ?? 'Помощник недоступен. Основная анкета продолжает работать.',
      );
    }
    return response.json();
  }
  health = () => this.request<{ status: string }>('/api/health');
  state = () => this.request<ChatState>('/api/chat/state');
  send = (text: string, messageId: string) =>
    this.request<ChatResult>('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_id: messageId, text }),
    });
}
