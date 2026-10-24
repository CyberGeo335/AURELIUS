"""Trusted local DEMO operator commands. Never exposed through borrower HTTP APIs."""
import argparse
import json
from pathlib import Path
from .repositories.postgres_config import PostgresConfig
from .repositories.operator_repository import approve_features,approve_product,resolve_profile,verify_field,pending_client_changes
from .services.lending import LendingService


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['features','approve-product','review','resolve-profile','verify-field','client-changes'])
    parser.add_argument('--reviewer',required=True)
    parser.add_argument('--case-id')
    parser.add_argument('--product-code',choices=['R01','R02','R03'],default='R01')
    parser.add_argument('--terms-id',type=int)
    parser.add_argument('--company-id',type=int)
    parser.add_argument('--field-code')
    parser.add_argument('--lender-case-id')
    parser.add_argument('--decision',choices=['OFFERED','DECLINED','REQUEST_DATA'])
    parser.add_argument('--reason')
    parser.add_argument('--input',type=Path,help='Explicit feature inputs, approval metadata or offer JSON')
    args=parser.parse_args()
    config=PostgresConfig.from_env()
    data=json.loads(args.input.read_text()) if args.input else None
    if args.action=='client-changes':
        print(json.dumps(pending_client_changes(config,args.case_id),ensure_ascii=False,default=str,indent=2))
    elif args.action=='features':
        if not args.case_id or data is None:parser.error('--case-id and --input are required')
        print(approve_features(config,args.case_id,args.product_code,data,args.reviewer))
    elif args.action=='approve-product':
        if not args.terms_id or data is None:parser.error('--terms-id and --input are required')
        approve_product(config,args.terms_id,data,args.reviewer)
        print('Product version approved for DEMO checks; refresh the case evidence.')
    elif args.action=='resolve-profile':
        if not args.company_id or data is None:parser.error('--company-id and --input are required')
        print(resolve_profile(config,args.company_id,data,args.reviewer))
    elif args.action=='verify-field':
        if not args.case_id or not args.field_code or data is None:parser.error('--case-id, --field-code and --input are required')
        verify_field(config,args.case_id,args.product_code,args.field_code,data,args.reviewer)
        print('Field verified with evidence; refresh case data to create a new immutable snapshot.')
    else:
        if not args.lender_case_id or not args.decision or not args.reason:parser.error('--lender-case-id, --decision and --reason are required')
        result=LendingService(config).review(args.lender_case_id,reviewer=args.reviewer,decision=args.decision,reason=args.reason,offer=data)
        print(json.dumps({'lender_case_id':result['lender_case_id'],'status':result['status'],'mode':'DEMO'}))


if __name__=='__main__':
    main()
