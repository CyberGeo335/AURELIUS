import type { Application } from './types';
export function requiredChecks(app: Application) {
  const authority = app.companyId === 'zerno' || app.reasonCode.includes('AUTHORITY_UNVERIFIED');
  const revenue = app.companyId === 'zerno' || app.reasonCode.includes('DATA_CONFLICT');
  return {
    authority,
    revenue,
    ready: (!authority || !!app.checks?.authority) && (!revenue || !!app.checks?.revenue),
  };
}
