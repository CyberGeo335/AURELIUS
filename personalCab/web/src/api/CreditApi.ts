import type { Application, BankAction, CreditState, Product, Profile } from '../domain/types';
export type DraftPatch = Partial<
  Pick<
    Application,
    | 'amount'
    | 'term'
    | 'purpose'
    | 'fields'
    | 'sources'
    | 'flow'
    | 'existing'
    | 'leasing'
    | 'businessConfirmed'
    | 'statement'
    | 'consentBki'
    | 'consentData'
    | 'step'
    | 'scenario'
    | 'files'
  >
>;
export interface CreditApi {
  getSnapshot: () => CreditState;
  subscribe: (listener: () => void) => () => void;
  createDraft: (profile: Profile, product: Product) => Promise<string>;
  saveDraft: (id: string, patch: DraftPatch) => Promise<void>;
  submit: (id: string) => Promise<void>;
  revise: (id: string, amount: number, term: number) => Promise<void>;
  answerRequest: (id: string, requestId: string, answer: string, file?: string) => Promise<void>;
  bankDecision: (id: string, revision: number, action: BankAction, reason: string) => Promise<void>;
  accept: (id: string, offerId: string) => Promise<void>;
  sign: (id: string) => Promise<void>;
  fund: (id: string) => Promise<void>;
  cancel: (id: string) => Promise<void>;
  reset: () => Promise<void>;
  tick: () => Promise<void>;
}
