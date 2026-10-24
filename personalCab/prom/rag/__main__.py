"""Offline check: python -m personalCab.prom.rag 'Какой формат ИНН R01 ООО?'"""
import argparse

from .pipeline import RequirementsRAG


def main():
    parser = argparse.ArgumentParser(description='Поиск требований к кредитным заявкам через FAISS/LangGraph')
    parser.add_argument('query')
    parser.add_argument('--product', action='append', default=[], help='Контекст продукта, например R01')
    parser.add_argument('--legal-form', choices=['IP', 'OOO', 'AO', 'OTHER'])
    args = parser.parse_args()
    print(RequirementsRAG().ask(args.query, args.product, args.legal_form).model_dump_json(indent=2))


if __name__ == '__main__':
    main()
