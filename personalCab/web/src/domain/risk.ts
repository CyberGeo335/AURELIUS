import type { Application } from './types';

// Risk and debt coverage are independent. Only expose the synthetic assessments
// supplied in the V2 reference; unknown risk is never inferred from coverage.
export function demoRisk(app: Application): { label: string; pd: string; tone: string } {
  if (app.companyId === 'zerno')
    return { label: 'Умеренный', pd: '4,8%', tone: 'status-NEEDS_INFO' };
  if (app.companyId === 'potok') return { label: 'Низкий', pd: '—', tone: 'status-OFFERED' };
  return { label: 'Нет оценки', pd: '—', tone: '' };
}
