const employeeReasonCodes = new Set(['BANK_APPROVE', 'BANK_REJECT', 'BANK_REQUEST_DATA']);

/** Exact codes: BANK_CONFIRMATION_REQUIRED is an internal scoring reason. */
export function clientVisibleReasons<T extends { code: string; message: string }>(
  reasons: readonly T[],
) {
  return reasons.filter((reason) => employeeReasonCodes.has(reason.code));
}
