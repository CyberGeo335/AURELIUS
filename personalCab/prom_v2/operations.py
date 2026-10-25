"""Private recovery journal. Preparing never executes an application command."""
import hashlib
import json
from psycopg.types.json import Jsonb
from .repository import Conflict


class Operations:
    def __init__(self, config):
        self.config = config

    def pending(self, account):
        with self.config.connect() as db:
            return db.execute(
                "SELECT p.request_id,p.body,EXISTS(SELECT 1 FROM aurelius_agent_v2.action_receipts r "
                "WHERE r.login=p.login AND r.request_id=p.request_id) AS completed "
                "FROM aurelius_agent_v2.pending_operations p WHERE p.login=%s "
                "AND p.created_at>now()-interval '8 hours' ORDER BY p.created_at",
                (account['login'],),
            ).fetchall()

    def prepare(self, account, body):
        if not isinstance(body, dict) or not isinstance(body.get('request_id'), str) or not 1 <= len(body['request_id']) <= 120:
            raise ValueError('Explicit request_id required')
        digest = hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        with self.config.connect() as db:
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('agent-v2:v2-'+account['login'],))
            db.execute("DELETE FROM aurelius_agent_v2.pending_operations WHERE login=%s AND created_at<=now()-interval '8 hours'",(account['login'],))
            existing = db.execute('SELECT input_hash FROM aurelius_agent_v2.pending_operations WHERE login=%s AND request_id=%s',
                                  (account['login'],body['request_id'])).fetchone()
            if existing:
                if existing['input_hash'] != digest:
                    raise Conflict('REQUEST_ID_REUSED')
                return {'prepared': True}
            count = db.execute('SELECT count(*) AS n FROM aurelius_agent_v2.pending_operations WHERE login=%s',(account['login'],)).fetchone()['n']
            if count >= 20:
                raise ValueError('Resolve previous operations first')
            db.execute('INSERT INTO aurelius_agent_v2.pending_operations(login,request_id,input_hash,body) VALUES(%s,%s,%s,%s)',
                       (account['login'],body['request_id'],digest,Jsonb(body)))
        return {'prepared': True}

    def acknowledge(self, account, request_id):
        if not isinstance(request_id,str):
            raise ValueError('request_id required')
        with self.config.connect() as db:
            db.execute('DELETE FROM aurelius_agent_v2.pending_operations WHERE login=%s AND request_id=%s',
                       (account['login'],request_id))
        return {'acknowledged': True}
