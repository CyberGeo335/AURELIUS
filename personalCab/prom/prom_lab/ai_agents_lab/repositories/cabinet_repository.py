"""Trusted, same-origin DEMO controls; no role/company grants come from chat."""
from datetime import datetime,timedelta,timezone
import json
from uuid import uuid4

from ..services.identifiers import stable_hash
from ..repositories.case_repository import AccessDenied,ConflictError,check_access
from ..schemas.models import Scope,Status


class CabinetRepository:
    def __init__(self,repository,allowed_company_ids):
        self.repository=repository
        self.allowed_company_ids=set(allowed_company_ids)
        if not hasattr(repository,'config'):
            with repository.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS web_profiles(actor_id TEXT PRIMARY KEY,company_id INTEGER)')
                db.execute('CREATE TABLE IF NOT EXISTS consents(actor_id TEXT,company_id INTEGER,scope TEXT,granted_at TEXT,expires_at TEXT,revoked_at TEXT,PRIMARY KEY(actor_id,company_id,scope))')
                db.execute('CREATE TABLE IF NOT EXISTS control_receipts(actor_id TEXT,request_id TEXT,input_hash TEXT,payload TEXT,PRIMARY KEY(actor_id,request_id))')

    def execute(self,actor,session,request_id,kind,arguments):
        digest=stable_hash([kind,arguments])
        with self.repository.actor_lock(actor.actor_id):
            with self.repository.connect() as db:
                receipt=db.execute('SELECT input_hash,payload FROM control_receipts WHERE actor_id=? AND request_id=?',(actor.actor_id,request_id)).fetchone()
                if receipt:
                    if receipt['input_hash']!=digest:
                        raise ConflictError('Control request ID reused with different arguments')
                    return json.loads(receipt['payload'])
                if kind=='new_session':
                    if arguments:
                        raise ValueError('New session accepts no arguments')
                    row=db.execute('SELECT case_id FROM credit_sessions WHERE owner_id=? AND session_id=?',(actor.actor_id,session)).fetchone()
                    if row:
                        case=self.repository.load(row['case_id'],actor)
                        if case.status not in {Status.CANCELLED,Status.COMPLETED}:
                            raise ConflictError('Finish or cancel the current case before starting a new one')
                    result={'session_id':'session-'+uuid4().hex}
                    db.execute('UPDATE web_clients SET session_id=? WHERE actor_id=?',(result['session_id'],actor.actor_id))
                elif kind=='company':
                    if set(arguments)!={'company_id'} or type(arguments['company_id']) is not int or arguments['company_id'] not in self.allowed_company_ids:
                        raise AccessDenied('COMPANY_NOT_AUTHORIZED')
                    company=arguments['company_id']
                    db.execute('INSERT INTO web_profiles(actor_id,company_id) VALUES(?,?) ON CONFLICT(actor_id) DO UPDATE SET company_id=excluded.company_id',(actor.actor_id,company))
                    result={'company_id':company,'session_id':'session-'+uuid4().hex}
                    db.execute('UPDATE web_clients SET session_id=? WHERE actor_id=?',(result['session_id'],actor.actor_id))
                elif kind=='select_case':
                    if set(arguments)!={'case_id'}:
                        raise ValueError('case_id is required')
                    case=self.repository.load(arguments['case_id'],actor)
                    result={'case_id':case.case_id,'session_id':'session-'+uuid4().hex}
                    db.execute('INSERT INTO credit_sessions(owner_id,session_id,case_id) VALUES(?,?,?)',(actor.actor_id,result['session_id'],case.case_id))
                    db.execute('UPDATE web_clients SET session_id=? WHERE actor_id=?',(result['session_id'],actor.actor_id))
                elif kind=='consent':
                    if set(arguments)!={'scope','granted'} or type(arguments['granted']) is not bool or not actor.company_id:
                        raise ValueError('Company, scope and explicit boolean consent required')
                    scope=Scope(arguments['scope'])
                    now=datetime.now(timezone.utc)
                    expires=now+timedelta(hours=1)
                    revoked=None if arguments['granted'] else now.isoformat()
                    db.execute('INSERT INTO consents(actor_id,company_id,scope,granted_at,expires_at,revoked_at) VALUES(?,?,?,?,?,?) ON CONFLICT(actor_id,company_id,scope) DO UPDATE SET granted_at=excluded.granted_at,expires_at=excluded.expires_at,revoked_at=excluded.revoked_at',
                               (actor.actor_id,actor.company_id,scope.value,now.isoformat(),expires.isoformat(),revoked))
                    result={'scope':scope.value,'granted':arguments['granted'],'expires_at':expires.isoformat()}
                else:
                    raise ValueError('Unknown control action')
                db.execute('INSERT INTO control_receipts(actor_id,request_id,input_hash,payload) VALUES(?,?,?,?)',(actor.actor_id,request_id,digest,json.dumps(result)))
        return result

    def applications(self,actor):
        with self.repository.connect() as db:
            rows=db.execute('SELECT payload FROM credit_cases WHERE owner_id=? AND borrower_id=? ORDER BY case_id',(actor.actor_id,actor.active_borrower_id)).fetchall()
        from ..schemas.models import Case
        cases=[Case.model_validate_json(row['payload']) for row in rows]
        for case in cases:
            check_access(case,actor)
        return [{'case_id':case.case_id,'revision':case.revision,'status':case.status,'request':case.request.model_dump(mode='json'),
                 'completed_module':5 if case.bank_application else 4 if case.assessment else 3 if case.data_context else 2 if case.product_selection else 1,
                 'application_ids':case.data_context.get('application_ids',{}) if case.data_context else {},
                 'assessment':case.assessment,'bank_application':self.lender_status(case,actor)} for case in cases]

    def lender_status(self,case,actor):
        check_access(case,actor)
        if hasattr(self.repository,'config') and case.result_refs.get('bank_application') and actor.has_consent(Scope.BANK_STATUS,case.request.borrower_id):
            with self.repository.config.connect(workflow=True) as db:
                row=db.execute('SELECT data FROM lender_cases WHERE lender_case_id=%s AND case_id=%s AND revision=%s',
                               (case.result_refs['bank_application'],case.case_id,case.revision)).fetchone()
                if row:return row['data']
        return case.bank_application

    def documents(self,case,actor):
        check_access(case,actor)
        if not hasattr(self.repository,'config'):
            return []
        with self.repository.config.connect(workflow=True) as db:
            rows=db.execute('SELECT document_id,filename,sha256,uploaded_at,extracted_data FROM evidence_documents WHERE case_id=%s AND owner_id=%s AND company_id=%s ORDER BY uploaded_at',
                            (case.case_id,actor.actor_id,actor.company_id)).fetchall()
        return [{'document_id':row['document_id'],'filename':row['filename'],'sha256':row['sha256'],
                 'uploaded_at':row['uploaded_at'].isoformat(),'status':row['extracted_data']['status']} for row in rows]

    def upload(self,case,actor,filename,encoded):
        check_access(case,actor)
        if not hasattr(self.repository,'config') or not actor.company_id:
            raise ValueError('Document storage requires PostgreSQL and a selected company')
        if not actor.has_consent(Scope.EVIDENCE_COLLECTION,case.request.borrower_id):
            raise AccessDenied('CONSENT_REQUIRED')
        if case.status in {Status.CANCELLED,Status.COMPLETED}:
            raise ConflictError('This case is closed')
        from ..services.documents import parse_document
        from psycopg.types.json import Jsonb
        content,media,digest,extracted=parse_document(filename,encoded)
        with self.repository.config.connect(workflow=True) as db:
            document_id='DOC-'+uuid4().hex
            db.execute('INSERT INTO evidence_documents(document_id,case_id,owner_id,company_id,filename,content_type,sha256,content,extracted_data) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(case_id,sha256) DO NOTHING',
                       (document_id,case.case_id,actor.actor_id,actor.company_id,filename,media,digest,content,Jsonb(extracted)))
        return self.documents(case,actor)
