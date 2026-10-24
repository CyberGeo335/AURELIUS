import { it, expect, vi, afterEach } from 'vitest';
import { HttpChatApi } from '../api/HttpChatApi';
afterEach(() => vi.unstubAllGlobals());
it('retries 428 once with the same message id and cookie credentials', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response('{}', { status: 428 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ result: { message: 'Готово' } }), { status: 200 }),
    );
  vi.stubGlobal('fetch', fetch);
  const response = await new HttpChatApi().send('Нужен кредит', 'message-1');
  expect(response.result.message).toBe('Готово');
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
  expect(fetch.mock.calls[1][1].credentials).toBe('include');
});
it.each([400, 409, 503])(
  'handles HTTP %i without automatic duplicate submission',
  async (status) => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status }));
    vi.stubGlobal('fetch', fetch);
    await expect(new HttpChatApi().send('Запрос', 'message-2')).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  },
);
it('explains an unreachable helper', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
  await expect(new HttpChatApi().state()).rejects.toThrow('Заявку можно заполнить через форму');
});
