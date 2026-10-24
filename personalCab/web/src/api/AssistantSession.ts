import type { ChatCandidate } from './HttpChatApi';
import type { Profile } from '../domain/types';
export interface AssistantSession {
  messages: { role: string; text: string }[];
  facts: Record<string, unknown>;
  quote: string;
  caseId?: string;
  candidates: ChatCandidate[];
  applicationId?: string;
  pending?: { id: string; text: string };
  lastMessageId?: string;
}
export const emptyAssistantSession = (): AssistantSession => ({
  messages: [],
  facts: {},
  quote: '',
  candidates: [],
});
export class AssistantSessionStore {
  read(profile: Profile): AssistantSession {
    try {
      return (
        JSON.parse(localStorage.getItem(`aurelius-assistant-${profile}`) ?? 'null') ??
        emptyAssistantSession()
      );
    } catch {
      return emptyAssistantSession();
    }
  }
  clear() {
    for (const profile of ['karpov', 'zerno'] as const)
      localStorage.removeItem(`aurelius-assistant-${profile}`);
  }
  save(profile: Profile, state: AssistantSession) {
    localStorage.setItem(`aurelius-assistant-${profile}`, JSON.stringify(state));
  }
}
