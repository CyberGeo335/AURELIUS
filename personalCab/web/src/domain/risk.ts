import type { Application } from './types';
// Kept for mock screen compatibility; no company-derived risk categories or PD.
export function demoRisk(_app: Application): { label: string; pd: string; tone: string } {
  return { label: '', pd: '—', tone: '' };
}
