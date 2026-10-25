import { HttpCreditApi } from '../api/HttpCreditApi';
import { HttpAuthApi } from '../api/HttpAuthApi';
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
import type { AuthApi, AuthSession, SignInInput, DemoLogin } from '../api/AuthApi';
import { MockAuthApi } from '../mocks/MockAuthApi';
import { MockCreditApi } from '../mocks/MockCreditApi';
export type Session = AuthSession;
const ApiContext = createContext<CreditApi | null>(null);
const SessionContext = createContext<{
  session: Session | null;
  loading: boolean;
  demoAccounts: readonly DemoLogin[];
  error: string;
  signIn: (input: SignInInput) => Promise<Session>;
  signOut: () => Promise<void>;
  restore: () => Promise<void>;
} | null>(null);
export function Providers({
  children,
  api: providedApi,
  authApi: providedAuthApi,
}: {
  children: ReactNode;
  api?: CreditApi;
  authApi?: AuthApi;
}) {
  const [api] = useState(
    () =>
      providedApi ??
      (import.meta.env.VITE_API_MODE === 'http' ? new HttpCreditApi() : new MockCreditApi()),
  );
  const [authApi] = useState(
    () =>
      providedAuthApi ??
      (import.meta.env.VITE_API_MODE === 'http' ? new HttpAuthApi() : new MockAuthApi()),
  );
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const restore = async () => {
    setLoading(true);
    setError('');
    try {
      const restored = await authApi.restore();
      if (api instanceof HttpCreditApi) {
        if (restored) await api.refresh();
        else api.clear();
      }
      setSession(restored);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось восстановить вход.');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    let active = true;
    void authApi
      .restore()
      .then(async (value) => {
        if (api instanceof HttpCreditApi) {
          if (value) await api.refresh();
          else api.clear();
        }
        if (active) setSession(value);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : 'Не удалось восстановить вход.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [authApi, api]);
  useEffect(() => {
    const timer = setInterval(() => {
      void api.tick().catch(() => {
        /* User mutations expose persistence failures. */
      });
    }, 600);
    return () => clearInterval(timer);
  }, [api]);
  const signIn = async (input: SignInInput) => {
    const value = await authApi.signIn(input);
    setError('');
    if (api instanceof HttpCreditApi) await api.refresh();
    setSession(value);
    return value;
  };
  const signOut = async () => {
    await authApi.signOut();
    if (api instanceof HttpCreditApi) api.clear();
    setSession(null);
  };
  return (
    <ApiContext value={api}>
      <SessionContext
        value={{
          session,
          loading,
          error,
          signIn,
          signOut,
          restore,
          demoAccounts: authApi.demoAccounts ?? [],
        }}
      >
        {children}
      </SessionContext>
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
export const useSession = () => {
  const value = useContext(SessionContext);
  if (!value) throw new Error('Session provider missing');
  return value;
};
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
