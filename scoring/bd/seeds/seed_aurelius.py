"""AURELIUS: 30 isolated demo scenarios for the *actual* schema_actual.sql.

pip install 'psycopg[binary]'
Set PG_PASSWORD and run: python seed_aurelius.py --dry-run
Then: python seed_aurelius.py --apply

No real PD or credit decisions are inserted. Existing data are never overwritten.
"""
import argparse
import csv
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

PREFIX = 'AURELIUS_DEMO_20261024'
TODAY = date.today()
NOW = datetime.now(timezone.utc)
SCENARIOS = [
 (1,'LLM','Нет ИНН','companies.inn','Запросить ИНН','R01','LEGAL_ENTITY','inn',None),
 (2,'LLM','Нет наименования','companies.name','Запросить наименование','R01','LEGAL_ENTITY','name',None),
 (3,'LLM','Нет ОГРН','companies.ogrn','Запросить ОГРН','R01','LEGAL_ENTITY','ogrn',None),
 (4,'LLM','Нет ОГРНИП','companies.ogrnip','Запросить ОГРНИП','R01','INDIVIDUAL_ENTREPRENEUR','ogrnip',None),
 (5,'LLM','Нет юридического адреса','companies.legal_address','Запросить юридический адрес','R01','LEGAL_ENTITY','legal_address',None),
 (6,'LLM','Нет ФИО руководителя','companies.director_name','Запросить ФИО руководителя','R01','LEGAL_ENTITY','director_name',None),
 (7,'LLM','Нет суммы кредита','credit_applications.requested_amount','Запросить сумму','R01','LEGAL_ENTITY','requested_amount',None),
 (8,'LLM','Нет срока кредита','credit_applications.requested_term_days','Запросить срок','R01','LEGAL_ENTITY','requested_term_days',None),
 (9,'LLM','Нет цели кредита','credit_applications.purpose','Запросить цель','R01','LEGAL_ENTITY','purpose',None),
 (10,'LLM','Полная заявка','Все обязательные поля','Подтвердить полноту','R01','LEGAL_ENTITY',None,None),
 (11,'SCORE','Высокий долг/выручка','current_debt_to_revenue ↑','Сравнить PD с базовым сценарием','R01','LEGAL_ENTITY',None,'high_debt'),
 (12,'SCORE','Низкий долг/выручка','current_debt_to_revenue ↓','Сравнить PD с базовым сценарием','R02','LEGAL_ENTITY',None,'low_debt'),
 (13,'SCORE','Низкий DSCR','current_dscr ↓','Сравнить PD с базовым сценарием','R03','LEGAL_ENTITY',None,'low_dscr'),
 (14,'SCORE','Высокий DSCR','current_dscr ↑','Сравнить PD с базовым сценарием','R01','LEGAL_ENTITY',None,'high_dscr'),
 (15,'SCORE','Низкий денежный резерв','current_cash_buffer_months ↓','Сравнить PD с базовым сценарием','R02','LEGAL_ENTITY',None,'low_cash'),
 (16,'SCORE','Высокий денежный резерв','current_cash_buffer_months ↑','Сравнить PD с базовым сценарием','R03','LEGAL_ENTITY',None,'high_cash'),
 (17,'SCORE','Падение выручки','current_revenue_trend_3m ↓','Сравнить PD с базовым сценарием','R01','LEGAL_ENTITY',None,'falling'),
 (18,'SCORE','Рост выручки','current_revenue_trend_3m ↑','Сравнить PD с базовым сценарием','R02','LEGAL_ENTITY',None,'rising'),
 (19,'SCORE','Комплексное ухудшение','DSCR ↓; долг ↑; резерв ↓; выручка ↓','Сравнить PD с базовым сценарием','R03','LEGAL_ENTITY',None,'stress'),
 (20,'SCORE','Финансовая устойчивость','DSCR ↑; долг ↓; резерв ↑; выручка ↑','Сравнить PD с базовым сценарием','R01','LEGAL_ENTITY',None,'strong'),
]
for n in range(21,31):
 SCENARIOS.append((n,'CONTROL',f'Обычная компания {n-20:02d}','Все обязательные поля; типовые финансы','Полная заявка; контрольный расчёт PD',('R01','R02','R03')[(n-21)%3], 'INDIVIDUAL_ENTREPRENEUR' if n in (23,26,29) else 'LEGAL_ENTITY',None,'normal'))


def inn_for(n, entity):
 # Synthetic stable identifiers; never use as real legal identifiers.
 if entity == 'LEGAL_ENTITY':
  first='990'+f'{n:06d}'
  check=sum(int(x)*w for x,w in zip(first,[2,4,10,3,5,9,4,6,8]))%11%10
  return first+str(check)
 first='990'+f'{n:07d}'
 c11=sum(int(x)*w for x,w in zip(first,[7,2,4,10,3,5,9,4,6,8]))%11%10
 eleven=first+str(c11)
 c12=sum(int(x)*w for x,w in zip(eleven,[3,7,2,4,10,3,5,9,4,6,8]))%11%10
 return eleven+str(c12)


def reg_for(n, entity):
 if entity == 'LEGAL_ENTITY':
  prefix='1990'+f'{n:08d}'
  return prefix+str(int(prefix)%11%10)
 prefix='3990'+f'{n:010d}'
 return prefix+str(int(prefix)%13%10)


def parameters(profile):
 d=dict(revenue=1_200_000,debt=1_000_000,payment=90_000,cash=1_200_000,expense=650_000,trend=0)
 if profile in ('high_debt','stress'): d.update(debt=18_000_000,payment=410_000)
 if profile in ('low_debt','strong'): d.update(debt=150_000,payment=12_000)
 if profile in ('low_dscr','stress'): d.update(expense=1_050_000,payment=360_000)
 if profile in ('high_dscr','strong'): d.update(expense=430_000,payment=18_000)
 if profile in ('low_cash','stress'): d.update(cash=40_000)
 if profile in ('high_cash','strong'): d.update(cash=9_000_000)
 if profile in ('falling','stress'): d.update(trend=-0.13)
 if profile in ('rising','strong'): d.update(trend=0.13)
 return d


def field_value(target, product, entity, company, application, details):
 # Representative questionnaire values; review non-trivial R02/R03 fields with product team.
 target=target.lower()
 if 'companies.inn' in target:return company['inn']
 if 'companies.ogrnip' in target:return company['ogrnip']
 if 'companies.ogrn' in target:return company['ogrn']
 if 'companies.entity_type' in target:return entity
 if 'companies.name' in target:return company['name']
 if 'companies.kpp' in target:return company['kpp']
 if 'companies.legal_address' in target:return company['legal_address']
 if 'companies.director_name' in target:return company['director_name']
 if 'companies.director_position' in target:return 'Генеральный директор'
 if 'companies.registration_date' in target:return str(company['registration_date'])
 if 'companies.status' in target:return 'ACTIVE'
 if 'companies.okved_main' in target:return '46.90'
 if 'companies.actual_activity_description' in target:return 'Оптовая торговля'
 if 'companies.actual_business_address' in target:return 'г. Москва, ул. Демонстрационная, 1'
 if 'companies.business_region' in target:return 'Москва'
 if 'companies.sme_category' in target:return 'SMALL'
 if 'companies.actual_activity_start_date' in target:return str(company['registration_date'])
 if 'companies.legal_form' in target:return 'ООО'
 if 'credit_applications.product_code' in target or 'credit_products.product_code' in target:return product
 if 'credit_applications.requested_amount' in target:return application['requested_amount']
 if 'credit_applications.requested_term_days' in target:return application['requested_term_days']
 if 'credit_applications.requested_term_months' in target:return 12
 if 'credit_applications.purpose' in target:return application['purpose']
 if 'application_details.contact_full_name' in target:return details['contact_full_name']
 if 'application_details.contact_role' in target:return 'Представитель'
 if 'application_details.contact_phone' in target:return '+79990000000'
 if 'application_details.signer_full_name' in target:return details['signer_full_name']
 if 'application_details.signer_authority_basis' in target:return 'Устав' if entity=='LEGAL_ENTITY' else 'Лично'
 if 'application_details.confirmed_at' in target:return NOW.isoformat()
 if 'application_details.guarantor_participation' in target:return False
 if 'application_details.proposed_collateral' in target or 'credit_products.requires_collateral' in target:return False
 return None


def run(apply):
 password=os.getenv('PG_PASSWORD')
 if not password: raise SystemExit('Укажите PG_PASSWORD (пароль PostgreSQL) в переменной окружения.')
 cfg=dict(host=os.getenv('PG_HOST','localhost'),port=int(os.getenv('PG_PORT','5433')),dbname=os.getenv('PG_DATABASE','business_scoring'),user=os.getenv('PG_USER','postgres'),password=password)
 records=[]
 with psycopg.connect(**cfg) as conn:
  with conn.cursor() as cur:
   cur.execute('SELECT product_code FROM credit_products WHERE product_code=ANY(%s)',(['R01','R02','R03'],))
   products={r[0] for r in cur.fetchall()}
   if products!={'R01','R02','R03'}:raise ValueError(f'В БД должны быть R01,R02,R03. Найдено: {products}')
   cur.execute('SELECT product_code,field_code,required_ip,required_ooo,target_db_field FROM application_field_requirements ORDER BY product_code,field_number')
   req={p:[] for p in products}
   for p,code,ip,ooo,target in cur.fetchall():
    if p in req:req[p].append((code,ip,ooo,target))
   if any(not req[p] for p in products):raise ValueError('Не заполнен application_field_requirements для R01/R02/R03')
   for n,kind,title,feature,expect,product,entity,missing,profile in SCENARIOS:
    inn=inn_for(n,entity)
    name=f'{PREFIX}_{n:02d} | {title}'
    cur.execute('SELECT company_id FROM companies WHERE inn=%s OR name=%s',(inn,name))
    existing=cur.fetchone()
    if existing:
     records.append(dict(scenario=f'AUR-{n:02d}',company_id=existing[0],application_id='existing',inn=inn,product=product,type=kind,status='ALREADY_EXISTS',scenario_name=title,expected=expect))
     continue
    mandatory=[(code,target) for code,ip,ooo,target in req[product] if (ooo if entity=='LEGAL_ENTITY' else ip)]
    omitted=[]
    for code,target in mandatory:
     if missing and missing in target.lower():omitted.append(code)
    if missing and not omitted:raise ValueError(f'AUR-{n:02d}: поле {missing} не обязательно для {product}/{entity}; измените сценарий')
    c=dict(inn=inn,name=name,ogrn=reg_for(n,entity) if entity=='LEGAL_ENTITY' else None,ogrnip=reg_for(n,entity) if entity!='LEGAL_ENTITY' else None,kpp='990001001' if entity=='LEGAL_ENTITY' else None,legal_address='г. Москва, ул. Демонстрационная, 1',director_name='Тестовый Руководитель' if entity=='LEGAL_ENTITY' else None,registration_date=TODAY-timedelta(days=900+n*3))
    a=dict(requested_amount=3_000_000,requested_term_days=365,purpose='Пополнение оборотных средств')
    details=dict(contact_full_name='Тестовый Контакт',signer_full_name='Тестовый Руководитель' if entity=='LEGAL_ENTITY' else 'Тестовый Предприниматель')
    # For nullable source fields, also leave main field empty; immutable registration fields stay intact.
    if missing in ('legal_address','director_name'):c[missing]=None
    if missing in a:a[missing]=None
    cur.execute('''INSERT INTO companies(entity_type,inn,ogrn,ogrnip,name,registration_date,status,status_date,okved_main,okved_main_name,legal_address,director_name,director_position,information_reliability_status,source_checked_at,kpp,legal_form,actual_activity_description,actual_business_address,business_region,business_city,sme_category,actual_activity_start_date)
      VALUES (%s,%s,%s,%s,%s,%s,'ACTIVE',%s,'46.90','Оптовая торговля',%s,%s,%s,'VERIFIED',%s,%s,%s,'Оптовая торговля','г. Москва, ул. Демонстрационная, 1','Москва','Москва','SMALL',%s) RETURNING company_id''',
      (entity,inn,c['ogrn'],c['ogrnip'],name,c['registration_date'],TODAY,c['legal_address'],c['director_name'],'Генеральный директор' if entity=='LEGAL_ENTITY' else None,NOW,c['kpp'],'ООО' if entity=='LEGAL_ENTITY' else None,c['registration_date']))
    cid=cur.fetchone()[0]
    cur.execute('''INSERT INTO credit_applications(company_id,product_code,requested_amount,requested_term_days,requested_term_months,purpose,application_status,missing_data_status)
      VALUES(%s,%s,%s,%s,%s,%s,'SUBMITTED',%s) RETURNING application_id''',(cid,product,a['requested_amount'],a['requested_term_days'],12 if a['requested_term_days'] else None,a['purpose'],'PARTIAL' if missing else 'COMPLETE'))
    aid=cur.fetchone()[0]
    cur.execute('''INSERT INTO application_details(application_id,guarantor_participation,proposed_collateral,contact_full_name,contact_role,contact_phone,signer_full_name,signer_authority_basis,confirmation_version,confirmed_at)
      VALUES(%s,FALSE,FALSE,%s,'Представитель','+79990000000',%s,'Устав','DEMO_V1',%s)''',(aid,details['contact_full_name'],details['signer_full_name'],NOW))
    # Populate the mandatory questionnaire keys from the actual live registry, not assumed R01_XX codes.
    for code,target in mandatory:
     if code in omitted:continue
     val=field_value(target,product,entity,c,a,details)
     if val is None:
      # Unknown product-specific fields intentionally remain unpopulated, never invent a fake answer.
      continue
     cur.execute('''INSERT INTO application_field_values(application_id,product_code,field_code,field_value,value_source,verification_status,changed_by_type)
        VALUES(%s,%s,%s,%s,'CLIENT','UNVERIFIED','SYSTEM')''',(aid,product,code,Jsonb(val)))
    d=parameters(profile)
    for year in (TODAY.year-1,TODAY.year):
     start=date(year,1,1)
     end=date(year,12,31) if year<TODAY.year else TODAY
     months=12 if year<TODAY.year else max(1,TODAY.month)
     revenue=d['revenue']*months
     cost=revenue*0.57
     operating_expenses=revenue*0.16
     operating_profit=revenue-cost-operating_expenses
     net=revenue*0.10
     cash=d['cash']
     liabilities=d['debt']+900_000
     assets=liabilities+max(1_500_000,cash)
     cur.execute('''INSERT INTO financial_statements(company_id,period_start,period_end,statement_type,revenue,cost_of_sales,gross_profit,operating_expenses,operating_profit,net_profit,total_assets,current_assets,cash_and_equivalents,short_term_liabilities,total_liabilities,equity,source_document_id,source_checked_at,is_verified)
       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)''',(cid,start,end,'ANNUAL' if year<TODAY.year else 'MANAGEMENT',revenue,cost,revenue-cost,operating_expenses,operating_profit,net,assets,max(cash+300_000,900_000),cash,600_000,liabilities,assets-liabilities,f'{PREFIX}-{n:02d}-{year}',NOW))
    # One year of transaction history, monthly cash flow with trend variants.
    for j in range(12):
     month=TODAY.month-j
     year=TODAY.year
     while month<=0:month+=12;year-=1
     dt=datetime(year,month, min(15,28),tzinfo=timezone.utc)
     factor=1.0+d['trend']*(11-j) if d['trend'] else 1.0
     inflow=max(100_000,round(d['revenue']*factor,2))
     outflow=round(d['expense']*max(0.5,factor),2)
     for direction,amount,category in [('IN',inflow,'REVENUE'),('OUT',outflow,'OTHER')]:
      cur.execute('''INSERT INTO bank_transactions(company_id,account_ref,bank_name,transaction_date,amount,direction,operation_category,payment_purpose,source_statement_id,source_checked_at)
        VALUES(%s,%s,'AURELIUS DEMO BANK',%s,%s,%s,%s,%s,%s,%s)''',(cid,f'{PREFIX}-{n:02d}',dt,amount,direction,category,'Синтетическая операция',f'{PREFIX}-{n:02d}-BANK',NOW))
    if d['debt']>0:
     cur.execute('''INSERT INTO credit_obligations(company_id,creditor_name,obligation_type,contract_ref,contract_date,maturity_date,original_amount,outstanding_balance,monthly_payment,overdue_amount,obligation_status)
       VALUES(%s,'AURELIUS DEMO BANK','LOAN',%s,%s,%s,%s,%s,%s,0,'ACTIVE') RETURNING obligation_id''',(cid,f'{PREFIX}-{n:02d}',TODAY-timedelta(days=700),TODAY+timedelta(days=700),d['debt']*1.2,d['debt'],d['payment']))
     oid=cur.fetchone()[0]
     for j in range(6):
      month=TODAY.month-j;year=TODAY.year
      while month<=0:month+=12;year-=1
      cur.execute('''INSERT INTO credit_repayment_history(obligation_id,period_date,scheduled_payment,actual_payment,outstanding_balance,overdue_amount,overdue_days,default_flag,observation_status,source_record_id,source_checked_at)
        VALUES(%s,%s,%s,%s,%s,0,0,FALSE,'ACTIVE',%s,%s)''',(oid,date(year,month,1),d['payment'],d['payment'],d['debt'],f'{PREFIX}-{n:02d}-REPAY',NOW))
    records.append(dict(scenario=f'AUR-{n:02d}',company_id=cid,application_id=aid,inn=inn,product=product,type=kind,status='INSERTED' if apply else 'DRY_RUN',scenario_name=title,expected=expect,missing_field_codes=';'.join(omitted)))
   if apply:conn.commit()
   else:conn.rollback()
 path=Path(__file__).with_name('aurelius_30_ids.csv')
 if apply:
  with path.open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in records))))
   w.writeheader();w.writerows(records)
 print(f'Режим: {"APPLY" if apply else "DRY RUN"}; сценариев: {len(records)}')
 for r in records:print(r['scenario'],r['type'],r['scenario_name'],r['company_id'],r['application_id'],r['status'])
 if apply:print('Реестр ID:',path)

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 g=parser.add_mutually_exclusive_group(required=True)
 g.add_argument('--dry-run',action='store_true');g.add_argument('--apply',action='store_true')
 args=parser.parse_args()
 run(args.apply)
