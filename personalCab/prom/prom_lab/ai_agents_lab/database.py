"""Explicit PostgreSQL setup and non-destructive import of legacy SQLite domain data."""
import argparse
from pathlib import Path
import sqlite3

from .repositories.postgres_config import PostgresConfig

ROOT = Path(__file__).resolve().parents[4]


def initialize(config):
    for migration in sorted((ROOT / 'scoring/bd/migrations').glob('*.sql')):
        with config.connect() as connection:
            connection.execute(migration.read_text(), prepare=False)
    from langgraph.checkpoint.postgres import PostgresSaver
    with config.connect(workflow=True, autocommit=True) as connection:
        PostgresSaver(connection).setup()


def import_sqlite(config, path):
    """All-or-nothing import, fail on differing existing keys; never delete either DB."""
    specs = {'credit_cases': ('case_id',), 'credit_sessions': ('owner_id','session_id'),
             'credit_receipts': ('owner_id','session_id','message_id'), 'web_clients': ('token',),
             'credit_audit': ('case_id','message_id','correlation_id')}
    legacy = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    legacy.row_factory = sqlite3.Row
    counts = {}
    try:
        with config.connect(workflow=True) as connection:
            from psycopg import sql
            for table, keys in specs.items():
                if not legacy.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?',(table,)).fetchone():
                    continue
                counts[table] = 0
                # Names come only from the fixed specs above, not caller input.
                for source in legacy.execute(f'SELECT * FROM {table}' + (' ORDER BY id' if table == 'credit_audit' else '')):
                    row = dict(source)
                    if table == 'credit_audit':
                        row.pop('id')
                    where = sql.SQL(' AND ').join(sql.SQL('{} IS NOT DISTINCT FROM %s').format(sql.Identifier(key)) for key in keys)
                    existing = connection.execute(sql.SQL('SELECT * FROM {} WHERE ').format(sql.Identifier(table)) + where, tuple(row[key] for key in keys)).fetchone()
                    if existing:
                        if any(existing[key] != value for key,value in row.items()):
                            raise ValueError(f'Conflicting legacy record in {table}; import rolled back')
                        continue
                    columns = list(row)
                    connection.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns)),tuple(row.values()))
                    counts[table] += 1
    finally:
        legacy.close()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--init-workflow',action='store_true')
    parser.add_argument('--import-sqlite',type=Path)
    parser.add_argument('--seed-clients',action='store_true')
    parser.add_argument('--credentials-output',type=Path)
    args = parser.parse_args()
    config = PostgresConfig.from_env()
    if args.init_workflow:
        initialize(config)
        print('PostgreSQL workflow schema and checkpoints initialized; public data preserved.')
    if args.import_sqlite:
        print(import_sqlite(config,args.import_sqlite))
    if args.seed_clients:
        import json
        import os
        from .services.client_auth import seed_clients
        if not args.credentials_output:
            parser.error('--credentials-output is required for newly generated passwords')
        # Exclusive, private file: never overwrite a previously issued credential list.
        with os.fdopen(os.open(args.credentials_output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:
            records=seed_clients(config)
            json.dump(records,output,ensure_ascii=False,indent=2)
        print(f'Created {len(records)} client accounts; credentials saved to {args.credentials_output}')
    if not args.init_workflow and not args.import_sqlite and not args.seed_clients:
        with config.connect() as connection:
            print(connection.execute('SELECT current_database() AS database, version() AS server').fetchone())


if __name__ == '__main__':
    main()
