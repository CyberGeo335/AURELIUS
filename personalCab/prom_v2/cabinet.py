"""Business-scoring v3 cabinet. Public records remain the source of truth.

Only the additive aurelius_cabinet schema holds sessions, versions and receipts.
No legacy account, lender-case or SQLite fallback is used by this boundary.
"""
import hashlib
import json
import os
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ApiError(Exception):
    def __init__(self, status, message, code="INVALID_REQUEST"):
        super().__init__(message)
        self.status, self.code = status, code


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def serial(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def positive(value, label, integer=False):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or (integer and number != int(number)):
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        raise ApiError(400, f"{label}: укажите положительное {'целое ' if integer else ''}число.")
    return int(number) if integer else number


class Cabinet:
    def __init__(self, database_url=None, scorer=None):
        self.url = database_url or os.getenv("DATABASE_URL")
        if not self.url:
            raise RuntimeError("Set DATABASE_URL for business_scoring")
        self.conninfo = self.url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.scorer = scorer

    def connect(self, autocommit=False):
        return psycopg.connect(self.conninfo, row_factory=dict_row, autocommit=autocommit,
                               connect_timeout=5)

    def initialize(self):
        # Deliberately execute only this additive migration, never older init scripts.
        source = Path(__file__).with_name("migrations") / "005_cabinet.sql"
        with self.connect() as db:
            db.execute(source.read_text(encoding="utf-8"), prepare=False)

    @staticmethod
    def public_user(row):
        return {key: row[key] for key in
                ("user_id", "login", "first_name", "last_name", "role", "company_id")}

    def login(self, login, password):
        if not isinstance(login, str) or not isinstance(password, str) or not login or not password:
            raise ApiError(400, "Введите логин и пароль.")
        with self.connect() as db:
            row = db.execute("SELECT * FROM public.user_accounts WHERE login=%s AND is_active",
                             (login,)).fetchone()
            # Plain-text comparison is the owner's explicit synthetic-demo contract.
            if not row or not secrets.compare_digest(row["password"].encode(), password.encode()):
                raise ApiError(401, "Неверный логин или пароль.", "LOGIN_REQUIRED")
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO aurelius_cabinet.sessions VALUES(%s,%s,now()+interval '8 hours')",
                       (digest(token), row["user_id"]))
            return token, self.public_user(row)

    def session(self, token):
        with self.connect() as db:
            row = db.execute("SELECT u.* FROM aurelius_cabinet.sessions s JOIN public.user_accounts u "
                             "USING(user_id) WHERE s.token_hash=%s AND s.expires_at>now() AND u.is_active",
                             (digest(token or ""),)).fetchone()
            if not row:
                raise ApiError(401, "Войдите в кабинет.", "LOGIN_REQUIRED")
            return self.public_user(row)

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM aurelius_cabinet.sessions WHERE token_hash=%s", (digest(token or ""),))

    @staticmethod
    def employee(user):
        if user["role"] != "BANK_EMPLOYEE":
            raise ApiError(403, "Действие доступно сотруднику банка.")

    @staticmethod
    def client(user):
        if user["role"] != "CLIENT" or user["company_id"] is None:
            raise ApiError(403, "Действие доступно клиенту.")

    @staticmethod
    def owned(db, user, application_id, lock=False):
        row = db.execute("SELECT * FROM public.credit_applications WHERE application_id=%s" +
                         (" FOR UPDATE" if lock else ""), (application_id,)).fetchone()
        if not row or (user["role"] != "BANK_EMPLOYEE" and row["company_id"] != user["company_id"]):
            raise ApiError(404, "Заявка не найдена.")
        return row

    def state(self, user):
        bank = user["role"] == "BANK_EMPLOYEE"
        with self.connect() as db:
            companies = db.execute("SELECT * FROM public.companies WHERE (%s OR company_id=%s) "
                                   "ORDER BY company_id", (bank, user["company_id"])).fetchall()
            apps = db.execute("SELECT * FROM public.credit_applications WHERE (%s OR company_id=%s) "
                              "ORDER BY application_date DESC,application_id DESC",
                              (bank, user["company_id"])).fetchall()
            return {"companies": companies, "applications": [self.project(db, a, bank) for a in apps],
                    "requirements": db.execute("SELECT * FROM public.application_field_requirements "
                                               "ORDER BY product_code,field_number").fetchall(),
                    "catalog": db.execute("SELECT t.* FROM public.credit_product_terms t "
                                          "JOIN public.credit_products p USING(product_code) WHERE p.active "
                                          "AND (effective_from IS NULL OR effective_from<=CURRENT_DATE) "
                                          "AND (effective_to IS NULL OR effective_to>=CURRENT_DATE)").fetchall()}

    @staticmethod
    def project(db, application, bank):
        aid = application["application_id"]
        meta = db.execute("SELECT * FROM aurelius_cabinet.application_state WHERE application_id=%s", (aid,)).fetchone()
        decision = db.execute("SELECT * FROM public.credit_decisions WHERE application_id=%s "
                              "ORDER BY decided_at DESC,decision_id DESC LIMIT 1", (aid,)).fetchone()
        offer = Cabinet.latest_offer(db, aid)
        # An unpublished calculation is only available to the reviewer.
        if not bank and (application["application_status"] != "APPROVED" or not offer or
                         offer["offer_status"] not in ("PROPOSED", "ACCEPTED")):
            offer = None
        if offer and not bank:
            offer = {key: offer[key] for key in ("offer_id", "offer_status", "offered_amount",
                     "offered_term_months", "offered_annual_rate_pct")}
        assessment = None
        if bank:
            snapshot = db.execute("SELECT snapshot_data FROM public.application_snapshots WHERE application_id=%s "
                                  "AND snapshot_type='DECISION' ORDER BY snapshot_version DESC LIMIT 1", (aid,)).fetchone()
            assessment = snapshot["snapshot_data"].get("assessment") if snapshot else None
        return {**application, "version": meta["version"] if meta else 1,
                "form_state": meta["form_state"] if meta else {},
                "decision": decision["decision"] if decision else None,
                "reasons": (decision or {}).get("reasons") or [], "offer": offer,
                "assessment": assessment,
                "details": db.execute("SELECT * FROM public.application_details WHERE application_id=%s", (aid,)).fetchone(),
                "product_details": db.execute("SELECT * FROM public.application_product_details WHERE application_id=%s", (aid,)).fetchone(),
                "fields": db.execute("SELECT * FROM public.application_field_values WHERE application_id=%s", (aid,)).fetchall(),
                "requests": db.execute("SELECT * FROM public.application_data_requests WHERE application_id=%s ORDER BY requested_at", (aid,)).fetchall(),
                "history": db.execute("SELECT event_id,action,details,created_at FROM aurelius_cabinet.events "
                                      "WHERE application_id=%s ORDER BY event_id DESC", (aid,)).fetchall()}

    def action(self, user, body):
        if body.get("kind") != "credit":
            raise ApiError(400, "Неподдерживаемая операция кабинета.")
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 120:
            raise ApiError(400, "Требуется request_id.")
        fingerprint = digest(json.dumps(body, sort_keys=True, ensure_ascii=False))
        aid = body.get("application_id")
        with self.connect(autocommit=True) as db:
            # Session locks span scoring's separate, committed SQLAlchemy transaction.
            keys = [f"cabinet-request:{user['user_id']}:{request_id}"]
            if aid is not None:
                keys.append(f"cabinet-application:{aid}")
            for key in keys:
                db.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (key,))
            try:
                receipt = db.execute("SELECT * FROM aurelius_cabinet.receipts WHERE user_id=%s AND request_id=%s",
                                     (user["user_id"], request_id)).fetchone()
                if receipt:
                    if receipt["input_hash"] != fingerprint:
                        raise ApiError(409, "Идентификатор запроса уже использован.", "REQUEST_ID_REUSED")
                    if not receipt["result"].get("pending_score"):
                        return receipt["result"]
                    aid = int(receipt["result"]["application_id"])
                    self.owned(db, user, aid)
                else:
                    with db.transaction():
                        aid = self.mutate(db, user, body)
                        result = {"application_id": str(aid)}
                        if body["action"] in ("submit", "score", "revise"):
                            result["pending_score"] = True
                        # Persist the domain mutation and its receipt atomically. A
                        # crash before/during scoring resumes this exact operation.
                        db.execute("INSERT INTO aurelius_cabinet.receipts VALUES(%s,%s,%s,%s)",
                                   (user["user_id"], request_id, fingerprint, Jsonb(result)))
                if body["action"] in ("submit", "score", "revise"):
                    self.score(aid)
                result = {"application_id": str(aid)}
                with db.transaction():
                    db.execute("UPDATE aurelius_cabinet.receipts SET result=%s WHERE user_id=%s AND request_id=%s",
                               (Jsonb(result), user["user_id"], request_id))
                return result
            finally:
                for key in reversed(keys):
                    db.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))

    def score(self, application_id):
        if self.scorer:
            return self.scorer(application_id, save=True)
        # Import through scoring's own package root to preserve the documented contract.
        import sys
        scoring_root = str(Path(__file__).resolve().parents[2] / "scoring")
        if scoring_root not in sys.path:
            sys.path.insert(0, scoring_root)
        from main.database import run_application
        from main.config import Settings
        from dataclasses import replace
        return run_application(application_id, save=True,
                               settings=replace(Settings.from_env(), database_url=self.url))

    def mutate(self, db, user, body):
        action = body.get("action")
        if action == "create":
            self.client(user)
            code = body.get("product")
            if code not in ("R01", "R02", "R03") or not db.execute(
                    "SELECT 1 FROM public.credit_products WHERE product_code=%s AND active", (code,)).fetchone():
                raise ApiError(400, "Выберите доступный продукт.")
            aid = db.execute("INSERT INTO public.credit_applications(company_id,product_code) VALUES(%s,%s) "
                             "RETURNING application_id", (user["company_id"], code)).fetchone()["application_id"]
            db.execute("INSERT INTO aurelius_cabinet.application_state(application_id) VALUES(%s)", (aid,))
            self.event(db, aid, user, action)
            return aid
        aid = body.get("application_id")
        app = self.owned(db, user, aid, lock=True)
        db.execute("INSERT INTO aurelius_cabinet.application_state(application_id) VALUES(%s) ON CONFLICT DO NOTHING", (aid,))
        meta = db.execute("SELECT * FROM aurelius_cabinet.application_state WHERE application_id=%s FOR UPDATE", (aid,)).fetchone()
        if type(body.get("expected_version")) is not int or body["expected_version"] != meta["version"]:
            raise ApiError(409, "Заявка изменилась. Обновите данные перед повтором.", "STALE_CASE_VERSION")
        if action in ("save", "submit", "revise", "answer", "accept", "cancel"):
            self.client(user)
        if action == "save":
            if app["application_status"] != "DRAFT":
                raise ApiError(409, "Редактировать можно только черновик.")
            self.save(db, app, body.get("patch", {}), meta["form_state"])
        elif action == "submit":
            if app["application_status"] != "DRAFT":
                raise ApiError(409, "Заявка уже отправлена.")
            self.validate_submission(db, app, meta["form_state"])
            db.execute("UPDATE public.credit_applications SET application_status='UNDER_REVIEW',missing_data_status='COMPLETE' "
                       "WHERE application_id=%s", (aid,))
            db.execute("UPDATE public.application_details SET confirmed_at=now(),confirmation_version='cabinet-v3-1' "
                       "WHERE application_id=%s", (aid,))
        elif action == "score":
            self.employee(user)
            if app["application_status"] not in ("SUBMITTED", "UNDER_REVIEW"):
                raise ApiError(409, "Скоринг доступен для отправленной заявки.")
        elif action == "review":
            self.employee(user)
            self.review(db, app, body)
        elif action == "accept":
            if app["application_status"] != "APPROVED":
                raise ApiError(409, "Нет одобренного предложения.")
            offer = self.latest_offer(db, aid)
            if not offer or str(offer["offer_id"]) != str(body.get("offer_id")) or offer["offer_status"] != "PROPOSED":
                raise ApiError(409, "Предложение изменилось.")
            db.execute("UPDATE public.application_product_terms SET offer_status='ACCEPTED' WHERE offer_id=%s", (offer["offer_id"],))
        elif action == "cancel":
            if app["application_status"] in ("REJECTED", "CANCELLED"):
                raise ApiError(409, "Заявка закрыта.")
            if db.execute("SELECT 1 FROM public.application_product_terms WHERE application_id=%s AND offer_status='ACCEPTED'", (aid,)).fetchone():
                raise ApiError(409, "Предложение уже принято.")
            db.execute("UPDATE public.credit_applications SET application_status='CANCELLED' WHERE application_id=%s", (aid,))
            db.execute("UPDATE public.application_product_terms SET offer_status='DECLINED' WHERE application_id=%s AND offer_status IN ('DRAFT','PROPOSED')", (aid,))
            db.execute("UPDATE public.application_data_requests SET request_status='CANCELLED' WHERE application_id=%s AND request_status='OPEN'", (aid,))
        elif action == "answer":
            if app["application_status"] != "AWAITING_DATA":
                raise ApiError(409, "Заявка не ожидает ответа.")
            request = db.execute("SELECT * FROM public.application_data_requests WHERE request_id=%s AND application_id=%s AND request_status='OPEN' FOR UPDATE", (body.get("data_request_id"), aid)).fetchone()
            answer = body.get("answer")
            if not request or not isinstance(answer, str) or not answer.strip():
                raise ApiError(400, "Укажите ответ на открытый запрос.")
            self.write_field(db, app, request["field_code"], answer)
            db.execute("UPDATE public.application_data_requests SET answer_value=%s,answered_at=now(),request_status='ANSWERED' WHERE request_id=%s", (Jsonb(answer), request["request_id"]))
            if not db.execute("SELECT 1 FROM public.application_data_requests WHERE application_id=%s AND request_status='OPEN'", (aid,)).fetchone():
                db.execute("UPDATE public.credit_applications SET application_status='UNDER_REVIEW' WHERE application_id=%s", (aid,))
        elif action == "revise":
            if app["application_status"] != "APPROVED" or not self.latest_offer(db, aid) or self.latest_offer(db, aid)["offer_status"] != "PROPOSED":
                raise ApiError(409, "Изменить можно только предложенные условия.")
            amount, term = positive(body.get("amount"), "Сумма"), positive(body.get("term"), "Срок", True)
            db.execute("UPDATE public.application_product_terms SET offer_status='DECLINED' WHERE application_id=%s AND offer_status IN ('DRAFT','PROPOSED')", (aid,))
            db.execute("UPDATE public.credit_applications SET requested_amount=%s,requested_term_months=%s,application_status='UNDER_REVIEW' WHERE application_id=%s", (amount, term, aid))
        else:
            raise ApiError(400, "Неизвестное действие.")
        db.execute("UPDATE aurelius_cabinet.application_state SET version=version+1,updated_at=now() WHERE application_id=%s", (aid,))
        self.event(db, aid, user, action)
        return aid

    @staticmethod
    def event(db, aid, user, action):
        db.execute("INSERT INTO aurelius_cabinet.events(application_id,user_id,action) VALUES(%s,%s,%s)", (aid, user["user_id"], action))

    @staticmethod
    def latest_offer(db, aid):
        # Use the offer of the latest calculation, never an old successful calculation
        # when the latest assessment has no offer. DECISION snapshots remain immutable.
        snapshot = db.execute("SELECT snapshot_data FROM public.application_snapshots WHERE application_id=%s AND snapshot_type='DECISION' ORDER BY snapshot_version DESC LIMIT 1", (aid,)).fetchone()
        if not snapshot:
            return None
        offer_id = snapshot["snapshot_data"].get("assessment", {}).get("persistence", {}).get("offer_id")
        if not offer_id:
            return None
        return db.execute("SELECT * FROM public.application_product_terms WHERE application_id=%s AND offer_id=%s", (aid, offer_id)).fetchone()

    @staticmethod
    def write_field(db, app, code, value):
        if not isinstance(value, str) or len(value) > 10000:
            raise ApiError(400, "Значение поля должно быть текстом до 10000 символов.")
        if not db.execute("SELECT 1 FROM public.application_field_requirements WHERE product_code=%s AND field_code=%s", (app["product_code"], code)).fetchone():
            raise ApiError(400, "Поле не относится к продукту.")
        old = db.execute("SELECT field_value FROM public.application_field_values WHERE application_id=%s AND field_code=%s", (app["application_id"], code)).fetchone()
        if old and old["field_value"] == value:
            return
        db.execute("INSERT INTO public.application_field_values(application_id,product_code,field_code,field_value,value_source,source_reference,obtained_at,verification_status,changed_by_type) VALUES(%s,%s,%s,%s,'CLIENT','cabinet',now(),'UNVERIFIED','CLIENT') ON CONFLICT(application_id,field_code) DO UPDATE SET field_value=EXCLUDED.field_value,value_source='CLIENT',obtained_at=now(),updated_at=now(),verification_status='UNVERIFIED',changed_by_type='CLIENT',source_reference='cabinet'", (app["application_id"], app["product_code"], code, Jsonb(value)))
        db.execute("INSERT INTO public.application_field_history(application_id,product_code,field_code,old_value,new_value,changed_by_type,source_type,verification_status) VALUES(%s,%s,%s,%s,%s,'CLIENT','CLIENT','UNVERIFIED')", (app["application_id"], app["product_code"], code, Jsonb(old["field_value"] if old else None), Jsonb(value)))

    def save(self, db, app, patch, previous):
        if not isinstance(patch, dict):
            raise ApiError(400, "Неверные данные формы.")
        aid = app["application_id"]
        amount = positive(patch["amount"], "Сумма") if "amount" in patch else app["requested_amount"]
        term = positive(patch["term"], "Срок", True) if "term" in patch else app["requested_term_months"]
        purpose = patch.get("purpose", app["purpose"])
        if purpose is not None and not isinstance(purpose, str):
            raise ApiError(400, "Неверная цель кредита.")
        db.execute("UPDATE public.credit_applications SET requested_amount=%s,requested_term_months=%s,purpose=%s WHERE application_id=%s", (amount, term, purpose, aid))
        for code, value in patch.get("fields", {}).items():
            self.write_field(db, app, code, value)
        # Store only application-specific details. Client edits never verify company facts.
        details = patch.get("details", {})
        allowed = {"contact_full_name", "contact_role", "contact_phone", "signer_full_name", "signer_authority_basis", "guarantor_participation", "proposed_collateral"}
        self.upsert_details(db, "application_details", aid, details, allowed)
        product = patch.get("product_details", {})
        allowed_product = {"max_tranche_term_value", "max_tranche_term_unit", "drawdown_period_months", "is_revolving", "overdraft_account_ref", "overdraft_bank_name", "overdraft_bank_bik"}
        self.upsert_details(db, "application_product_details", aid, product, allowed_product, app["company_id"])
        form = {**previous, **{key: patch[key] for key in ("consentBki", "consentData", "businessConfirmed", "step") if key in patch}}
        if any(key in form and type(form[key]) is not bool for key in ("consentBki", "consentData", "businessConfirmed")):
            raise ApiError(400, "Согласие должно быть явным.")
        db.execute("UPDATE aurelius_cabinet.application_state SET form_state=%s WHERE application_id=%s", (Jsonb(form), aid))

    @staticmethod
    def upsert_details(db, table, aid, values, allowed, company_id=None):
        from psycopg import sql
        if not isinstance(values, dict) or set(values) - allowed:
            raise ApiError(400, "Неизвестное поле анкеты.")
        if table == "application_details":
            db.execute("INSERT INTO public.application_details(application_id) VALUES(%s) ON CONFLICT DO NOTHING", (aid,))
        else:
            db.execute("INSERT INTO public.application_product_details(application_id,company_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (aid, company_id))
        for key, value in values.items():
            db.execute(sql.SQL("UPDATE public.{} SET {}=%s WHERE application_id=%s").format(sql.Identifier(table), sql.Identifier(key)), (None if value == "" else value, aid))

    @staticmethod
    def validate_submission(db, app, form):
        positive(app["requested_amount"], "Сумма")
        positive(app["requested_term_months"], "Срок", True)
        if not app["purpose"]:
            raise ApiError(400, "Укажите цель кредита.")
        if not all(form.get(key) is True for key in ("consentBki", "consentData", "businessConfirmed")):
            raise ApiError(400, "Подтвердите сведения и согласия.")
        missing = db.execute("SELECT r.field_label FROM public.application_field_requirements r JOIN public.companies c ON c.company_id=%s LEFT JOIN public.application_field_values v ON v.application_id=%s AND v.field_code=r.field_code WHERE r.product_code=%s AND CASE WHEN c.entity_type='INDIVIDUAL_ENTREPRENEUR' THEN r.required_ip ELSE r.required_ooo END AND (v.field_value IS NULL OR v.field_value IN ('null'::jsonb,'\"\"'::jsonb)) ORDER BY r.field_number", (app["company_id"], app["application_id"], app["product_code"])).fetchall()
        if missing:
            raise ApiError(400, "Заполните обязательные поля: " + "; ".join(r["field_label"] for r in missing))
        values = {r["field_code"]: r["field_value"] for r in db.execute("SELECT field_code,field_value FROM public.application_field_values WHERE application_id=%s", (app["application_id"],)).fetchall()}
        prefix = app["product_code"]
        company = db.execute("SELECT inn FROM public.companies WHERE company_id=%s", (app["company_id"],)).fetchone()
        if values.get(prefix + "_01") != prefix or (company["inn"] and values.get(prefix + "_03") != company["inn"]):
            raise ApiError(400, "Продукт и ИНН должны совпадать с данными заявки.")
        inn = values.get(prefix + "_03", "")
        if not inn.isdigit() or len(inn) not in (10, 12):
            raise ApiError(400, "ИНН должен содержать 10 или 12 цифр.")
        if positive(values.get(prefix + "_05"), "Сумма") != app["requested_amount"] or positive(values.get(prefix + "_06"), "Срок", True) != app["requested_term_months"]:
            raise ApiError(400, "Сумма и срок анкеты не совпадают с параметрами заявки.")
        if values.get(prefix + "_31") != "Подтверждаю":
            raise ApiError(400, "Подтвердите корректность анкеты.")
        if app["product_code"] in ("R02", "R03"):
            details = db.execute("SELECT * FROM public.application_product_details WHERE application_id=%s", (app["application_id"],)).fetchone()
            if not details or not details["max_tranche_term_value"] or details["max_tranche_term_unit"] not in ("DAYS", "MONTHS"):
                raise ApiError(400, "Укажите отдельный срок транша и единицу измерения.")

    def review(self, db, app, body):
        if app["application_status"] not in ("SUBMITTED", "UNDER_REVIEW", "AWAITING_DATA"):
            raise ApiError(409, "Заявка недоступна для решения.")
        decision, reason = body.get("decision"), body.get("reason")
        if decision not in ("APPROVE", "REJECT", "REQUEST_DATA") or not isinstance(reason, str) or not reason.strip():
            raise ApiError(400, "Укажите решение и его причину.")
        aid = app["application_id"]
        last = db.execute("SELECT * FROM public.credit_decisions WHERE application_id=%s ORDER BY decided_at DESC,decision_id DESC LIMIT 1", (aid,)).fetchone()
        if not last:
            raise ApiError(409, "Сначала выполните скоринг.")
        offer = self.latest_offer(db, aid)
        if decision == "APPROVE" and (not offer or offer["offer_status"] != "DRAFT"):
            raise ApiError(409, "Для одобрения нужен рассчитанный черновик предложения.")
        if decision == "APPROVE" and db.execute("SELECT 1 FROM public.application_data_requests WHERE application_id=%s AND request_status='OPEN'", (aid,)).fetchone():
            raise ApiError(409, "Сначала дождитесь ответов на открытые запросы.")
        if decision == "REQUEST_DATA":
            code = body.get("field_code")
            if not db.execute("SELECT 1 FROM public.application_field_requirements WHERE product_code=%s AND field_code=%s", (app["product_code"], code)).fetchone():
                raise ApiError(400, "Выберите поле для уточнения.")
            db.execute("INSERT INTO public.application_data_requests(application_id,product_code,field_code,question_text) VALUES(%s,%s,%s,%s)", (aid, app["product_code"], code, reason.strip()))
        db.execute("INSERT INTO public.credit_decisions(application_id,scoring_result_id,policy_version,eligibility_status,decision,approved_amount,reasons) VALUES(%s,%s,%s,%s,%s,%s,%s)", (aid, last["scoring_result_id"], last["policy_version"], "ELIGIBLE" if decision == "APPROVE" else "INELIGIBLE" if decision == "REJECT" else "NEEDS_DATA", decision, offer["offered_amount"] if decision == "APPROVE" else None, Jsonb([{"code": "BANK_" + decision, "message": reason.strip()}])))
        status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REQUEST_DATA": "AWAITING_DATA"}[decision]
        db.execute("UPDATE public.credit_applications SET application_status=%s,decision_date=now() WHERE application_id=%s", (status, aid))
        if decision == "APPROVE":
            db.execute("UPDATE public.application_product_terms SET offer_status='PROPOSED' WHERE offer_id=%s", (offer["offer_id"],))
        elif decision == "REJECT":
            db.execute("UPDATE public.application_product_terms SET offer_status='DECLINED' WHERE application_id=%s AND offer_status IN ('DRAFT','PROPOSED')", (aid,))
