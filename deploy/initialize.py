"""Validate a freshly restored seed once; apply only cabinet migrations."""
from personalCab.prom_v2.cabinet import Cabinet

cabinet = Cabinet()
expected = {'companies': 30, 'credit_applications': 30, 'user_accounts': 32,
            'risk_policy_parameters': 3, 'macro_indicators': 1}
with cabinet.connect() as db:
    # This schema/table is created by restore, never inferred for an existing DB.
    db.execute('LOCK TABLE aurelius_deploy.seed_validation IN EXCLUSIVE MODE')
    if not db.execute('SELECT 1 FROM aurelius_deploy.seed_validation').fetchone():
        from psycopg import sql
        for table, count in expected.items():
            actual = db.execute(sql.SQL('SELECT count(*) AS n FROM public.{}').format(sql.Identifier(table))).fetchone()['n']
            print(f'{table}: {actual} (expected {count})', flush=True)
            if actual != count:
                raise RuntimeError(f'Seed validation failed: {table}: {actual} != {count}')
        db.execute('INSERT INTO aurelius_deploy.seed_validation(singleton) VALUES (true)')
    else:
        print('Initial seed already validated; existing business data preserved.', flush=True)
cabinet.initialize()
print('Cabinet migrations 005–009 completed.', flush=True)
