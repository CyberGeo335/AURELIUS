from contextlib import contextmanager
import hashlib

from .case_repository import CaseRepository, ConflictError
from .postgres_config import PostgresConfig


class SQLConnection:
    """Adapt the existing repository's fixed SQL parameter notation; never user SQL."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        if query == 'BEGIN IMMEDIATE':
            query = 'SELECT 1'  # psycopg context already provides one atomic transaction.
        return self.connection.execute(query.replace('?', '%s'), params)


class PostgresCaseRepository(CaseRepository):
    def __init__(self, config: PostgresConfig):
        self.config = config
        with config.connect(workflow=True) as connection:
            if connection.execute("SELECT to_regclass('aurelius_workflow.credit_cases') AS name").fetchone()['name'] is None:
                raise RuntimeError('Run python -m personalCab.prom.prom_lab.ai_agents_lab.database --init-workflow first')

    @contextmanager
    def connect(self):
        with self.config.connect(workflow=True) as connection:
            yield SQLConnection(connection)

    @contextmanager
    def actor_lock(self, actor_id):
        key = int.from_bytes(hashlib.sha256(('aurelius:' + actor_id).encode()).digest()[:8], 'big', signed=True)
        with self.config.connect(autocommit=True) as connection:
            acquired = connection.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (key,)).fetchone()['acquired']
            if not acquired:
                raise ConflictError('Другое сообщение этого пользователя ещё обрабатывается')
            try:
                yield
            finally:
                connection.execute('SELECT pg_advisory_unlock(%s)', (key,))


def create_case_repository(database=None):
    if database is None or isinstance(database, PostgresConfig):
        return PostgresCaseRepository(database or PostgresConfig.from_env())
    # Explicit legacy/test mode only. Production/default runtime no longer selects SQLite.
    return CaseRepository(database)
