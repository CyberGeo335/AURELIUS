import { Card, SourceBadge } from '../components/v2/primitives';
import type { Application, Company, ServerRequirement } from '../domain/types';
import {
  companyFieldValue,
  fieldValue,
  sourceLabel,
  verificationLabel,
} from '../domain/provenance';

export function HttpProvenance({
  app,
  company,
  requirements,
}: {
  app: Application;
  company?: Company;
  requirements: readonly ServerRequirement[];
}) {
  const fields = app.server?.fields ?? [];
  const entity = company?.server?.entity_type;
  const applicable = requirements.filter(
    (r) =>
      r.product_code === app.product &&
      (entity === 'INDIVIDUAL_ENTREPRENEUR'
        ? r.required_ip
        : entity === 'LEGAL_ENTITY'
          ? r.required_ooo
          : true),
  );
  const codes = [
    ...new Set([...applicable.map((r) => r.field_code), ...fields.map((f) => f.field_code)]),
  ];
  return (
    <Card className="http-provenance">
      <h2>Анкета клиента</h2>
      {codes.length ? (
        <div className="table-scroll">
          <table aria-label="Происхождение данных анкеты">
            <thead>
              <tr>
                <th>Поле</th>
                <th>Значение</th>
                <th>Источник</th>
                <th>Статус проверки</th>
              </tr>
            </thead>
            <tbody>
              {codes.map((code) => {
                const field = fields.find((f) => f.field_code === code);
                const requirement = requirements.find(
                  (r) => r.product_code === app.product && r.field_code === code,
                );
                const value = field
                  ? field.field_value
                  : companyFieldValue(requirement?.target_db_field ?? '', company?.server);
                const status = verificationLabel(field?.verification_status);
                return (
                  <tr
                    key={code}
                    className={
                      field?.verification_status === 'CONFLICT' ? 'is-conflict' : undefined
                    }
                  >
                    <th scope="row">{requirement?.field_label ?? code}</th>
                    <td>{fieldValue(value)}</td>
                    <td>
                      <SourceBadge>{sourceLabel(field?.value_source)}</SourceBadge>
                    </td>
                    <td>
                      <span className={`status http-provenance-status ${status.tone}`}>
                        {status.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">Данных анкеты пока нет.</p>
      )}
    </Card>
  );
}
