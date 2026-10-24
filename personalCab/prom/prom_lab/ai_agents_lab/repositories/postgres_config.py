"""PostgreSQL configuration. Never put passwords into command-line arguments/logs."""
from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class PostgresConfig:
    host: str = 'localhost'
    port: int = 5433
    dbname: str = 'business_scoring'
    user: str = 'postgres'
    password: str | None = field(default=None, repr=False)
    conninfo: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls):
        return cls(host=os.getenv('PG_HOST', os.getenv('PGHOST', 'localhost')),
                   port=int(os.getenv('PG_PORT', os.getenv('PGPORT', '5433'))),
                   dbname=os.getenv('PG_DATABASE', os.getenv('PGDATABASE', 'business_scoring')),
                   user=os.getenv('PG_USER', os.getenv('PGUSER', 'postgres')),
                   password=os.getenv('PG_PASSWORD') or os.getenv('PGPASSWORD'),
                   conninfo=os.getenv('AURELIUS_DATABASE_URL'))

    def connect(self, *, workflow=False, autocommit=False):
        import psycopg
        from psycopg.rows import dict_row
        kwargs = {'connect_timeout': 5, 'row_factory': dict_row, 'autocommit': autocommit,
                  'prepare_threshold': 0}
        if workflow:
            kwargs['options'] = '-c search_path=aurelius_workflow,public'
        if self.conninfo:
            return psycopg.connect(self.conninfo, **kwargs)
        kwargs.update(host=self.host, port=self.port, dbname=self.dbname, user=self.user)
        if self.password is not None:
            kwargs['password'] = self.password
        return psycopg.connect(**kwargs)
