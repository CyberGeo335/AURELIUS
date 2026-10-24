import {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import type { CreditApi } from '../api/CreditApi';
import type { Profile } from '../domain/types';
import { MockCreditApi } from '../mocks/MockCreditApi';
export type Session = { role: 'client' | 'bank'; profile: Profile };
const ApiContext = createContext<CreditApi | null>(null);
const SessionContext = createContext<{
  session: Session | null;
  login: (session: Session | null) => void;
}>({ session: null, login: () => {} });
export function Providers({
  children,
  api: providedApi,
}: {
  children: ReactNode;
  api?: CreditApi;
}) {
  const [api] = useState(() => providedApi ?? new MockCreditApi());
  const [session, setSession] = useState<Session | null>(() => {
    try {
      const s = JSON.parse(sessionStorage.getItem('aurelius-session') ?? 'null');
      return s && ['client', 'bank'].includes(s.role) && ['karpov', 'zerno'].includes(s.profile)
        ? s
        : null;
    } catch {
      return null;
    }
  });
  useEffect(() => {
    const timer = setInterval(() => {
      void api.tick().catch(() => {
        /* User mutations expose persistence failures. */
      });
    }, 600);
    return () => clearInterval(timer);
  }, [api]);
  const login = (value: Session | null) => {
    sessionStorage.setItem('aurelius-session', JSON.stringify(value));
    setSession(value);
  };
  return (
    <ApiContext value={api}>
      <SessionContext value={{ session, login }}>{children}</SessionContext>
    </ApiContext>
  );
}
export const useApi = () => {
  const api = useContext(ApiContext);
  if (!api) throw new Error('CreditApi provider missing');
  return api;
};
export const useCredit = () => {
  const api = useApi();
  return useSyncExternalStore(api.subscribe, api.getSnapshot);
};
export const useSession = () => useContext(SessionContext);
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lastAction = useRef<(() => Promise<unknown>) | null>(null);
  const run = async (action: () => Promise<unknown>) => {
    if (busy) return;
    lastAction.current = action;
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Не удалось выполнить действие. Повторите попытку.',
      );
    } finally {
      setBusy(false);
    }
  };
  return {
    busy,
    error,
    setError,
    run,
    retry: () => {
      if (lastAction.current) void run(lastAction.current);
    },
  };
}
