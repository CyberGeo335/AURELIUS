import { afterEach, expect, it, vi } from 'vitest';
import { requestId } from '../domain/requestId';

afterEach(() => vi.unstubAllGlobals());
it('generates unique UUID v4 request IDs without secure-context randomUUID', () => {
  const crypto = globalThis.crypto;
  vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) });
  const ids = Array.from({ length: 100 }, requestId);
  expect(new Set(ids).size).toBe(100);
  for (const id of ids)
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
