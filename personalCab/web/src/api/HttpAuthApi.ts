import type { AuthApi, AuthSession, SignInInput } from './AuthApi';
import { HttpV2Api } from './HttpV2Api';

interface UserV3 {
  user_id: number;
  login: string;
  first_name: string;
  last_name: string;
  role: 'CLIENT' | 'BANK_EMPLOYEE';
  company_id: number | null;
}
export class HttpAuthApi implements AuthApi {
  readonly demoAccounts = [];
  constructor(private http = new HttpV2Api()) {}
  private session(user: UserV3): AuthSession {
    return {
      userId: String(user.user_id),
      username: user.login,
      firstName: user.first_name,
      lastName: user.last_name,
      role: user.role === 'BANK_EMPLOYEE' ? 'bank' : 'client',
      profile: user.company_id === null ? '' : String(user.company_id),
    };
  }
  restore = async () => {
    try {
      return this.session(await this.http.request<UserV3>('session'));
    } catch (error) {
      if ((error as { status?: number }).status === 401) return null;
      throw error;
    }
  };
  signIn = async (input: SignInInput) =>
    this.session(
      await this.http.request<UserV3>('login', { login: input.username, password: input.password }),
    );
  signOut = async () => {
    await this.http.logout();
  };
}
