import type { Profile } from '../domain/types';
export type Role = 'client' | 'bank';
export interface SignInInput {
  role: Role;
  firstName: string;
  lastName: string;
  username: string;
  password: string;
}
export interface AuthSession {
  userId: string;
  role: Role;
  profile: Profile;
  firstName: string;
  lastName: string;
  username: string;
}
export interface DemoLogin extends SignInInput {
  userId: string;
  profile: Profile;
  label: string;
}
// A server adapter must return trusted identity and company access; never derive them from the form.
export interface AuthApi {
  readonly demoAccounts?: readonly DemoLogin[];
  restore: () => Promise<AuthSession | null>;
  signIn: (input: SignInInput) => Promise<AuthSession>;
  signOut: () => Promise<void>;
}
export function validateSignIn(input: SignInInput) {
  const errors: Partial<Record<keyof SignInInput, string>> = {};
  for (const field of ['firstName', 'lastName'] as const) {
    if (!input[field].trim())
      errors[field] = field === 'firstName' ? 'Укажите имя' : 'Укажите фамилию';
    else if (input[field].trim().length > 60) errors[field] = 'Не более 60 символов';
  }
  if (!input.username.trim()) errors.username = 'Введите логин';
  else if (input.username.trim().length > 80) errors.username = 'Не более 80 символов';
  if (!input.password) errors.password = 'Введите пароль';
  else if (input.password.length > 128) errors.password = 'Не более 128 символов';
  return errors;
}
