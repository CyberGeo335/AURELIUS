"""Read-only source checks for extended docs; no runtime/DB/model execution.

Run from the repository root: python docs/extended/check_docs.py
"""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs/extended'


def slug(text):
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text).strip().lower()
    text = re.sub(r'[^\w\- ]', '', text, flags=re.UNICODE)
    return text.replace(' ', '-')


def anchors(path):
    found = set()
    used = {}
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', path.read_text(encoding='utf-8-sig'), re.M):
        key = slug(heading)
        number = used.get(key, 0)
        used[key] = number + 1
        found.add(key if number == 0 else f'{key}-{number}')
    return found


def closing(text, start):
    """Balance TS source delimiters, ignoring quoted strings and comments."""
    pairs = {'(': ')', '[': ']', '{': '}'}
    stack = [pairs[text[start]]]
    quote = None
    i = start + 1
    while i < len(text):
        char = text[i]
        if quote:
            if char == '\\':
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif text[i:i + 2] == '//':
            i = text.find('\n', i)
            if i < 0:
                break
            continue
        elif text[i:i + 2] == '/*':
            i = text.index('*/', i + 2) + 2
            continue
        elif char in pairs:
            stack.append(pairs[char])
        elif char in ')]}':
            if char != stack.pop():
                raise ValueError('Unbalanced source')
            if not stack:
                return i
        i += 1
    raise ValueError('Unclosed source')


def array_count(text, start):
    end = closing(text, start)
    cursor = start + 1
    count = 0
    while cursor < end:
        if text[cursor].isspace() or text[cursor] == ',':
            cursor += 1
            continue
        count += 1
        while cursor < end and text[cursor] != ',':
            char = text[cursor]
            if char in '([{':
                cursor = closing(text, cursor) + 1
            elif char in "'\"`":
                quote = char
                cursor += 1
                while cursor < end:
                    if text[cursor] == '\\':
                        cursor += 2
                    elif text[cursor] == quote:
                        cursor += 1
                        break
                    else:
                        cursor += 1
            else:
                cursor += 1
    return count


def frontend_inventory():
    result = []
    for path in sorted((ROOT / 'personalCab/web/src/test').glob('*.test.*')):
        text = path.read_text(encoding='utf-8')
        scopes = []
        def each_count(argument):
            if text[argument] == '[':
                return array_count(text, argument)
            name = re.match(r'\w+', text[argument:]).group()
            source = text
            if name == 'demoAccounts':
                source = (ROOT / 'personalCab/web/src/mocks/MockAuthApi.ts').read_text(encoding='utf-8')
            assignment = re.search(r'\bconst\s+' + name + r'(?:\s*:[^=]+)?\s*=\s*\[', source)
            if not assignment:
                raise ValueError(f'Unresolved each table {name}')
            return array_count(source, assignment.end() - 1)
        for group in re.finditer(r'\bdescribe\.each\s*\(\s*', text):
            count = each_count(group.end())
            first_close = closing(text, text.index('(', group.start()))
            arrow = text.index('=>', first_close)
            block = text.index('{', arrow)
            scopes.append((block, closing(text, block), count))
        cases = 0
        definitions = 0
        for test in re.finditer(r'\b(?:it|test)(\.each)?\s*\(\s*', text):
            count = each_count(test.end()) if test.group(1) else 1
            definitions += 1
            for left, right, multiplier in scopes:
                if left < test.start() < right:
                    count *= multiplier
            cases += count
        result.append({'path': path.relative_to(ROOT).as_posix(), 'definitions': definitions, 'static_cases': cases})
    return result


def main():
    errors = []
    links = 0
    documents = sorted(DOCS.rglob('*.md'))
    pattern = r'\]\((<?(?:[^()\s]|\([^()]*\))+>?)\)'
    for document in documents:
        text = document.read_text(encoding='utf-8-sig')
        text = re.sub(r'```.*?```', '', text, flags=re.S)
        for target in re.findall(pattern, text):
            target = target.strip('<>')
            if re.match(r'^[a-zA-Z]+:', target):
                continue
            links += 1
            rel, _, fragment = unquote(target).partition('#')
            dest = document.parent / rel if rel else document
            if not dest.exists():
                errors.append(f'{document.relative_to(ROOT)}: missing {target}')
            elif fragment and dest.suffix == '.md' and fragment not in anchors(dest):
                errors.append(f'{document.relative_to(ROOT)}: missing anchor {target}')

    inventory = []
    directories = ['personalCab/prom_v2/tests', 'personalCab/prom/prom_lab/ai_agents_lab/tests',
                   'scoring/main/tests', 'deploy/tests']
    selected_legacy = {'test_client_validation.py', 'test_extractor.py'}
    for directory in directories:
        for path in sorted((ROOT / directory).glob('test_*.py')):
            if 'ai_agents_lab' in directory and path.name not in selected_legacy:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            functions = 0
            cases = 0
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith('test_'):
                    continue
                functions += 1
                count = 1
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'parametrize':
                        values = decorator.args[1]
                        if not isinstance(values, (ast.List, ast.Tuple)):
                            errors.append(f'{path.relative_to(ROOT)}: unresolved parametrization {node.name}')
                        else:
                            count *= len(values.elts)
                cases += count
            inventory.append({'path': path.relative_to(ROOT).as_posix(), 'functions': functions, 'static_cases': cases})

    model = ROOT / 'scoring/main/ml_scoring/model'
    config = json.loads((model / 'best_config.json').read_text(encoding='utf-8'))
    actual_sha = hashlib.sha256((model / 'best_model.cbm').read_bytes()).hexdigest()
    if actual_sha != config['model_sha256']:
        errors.append('model SHA mismatch')
    schema_path = ROOT / 'scoring/bd/v_4 (actual)/schema_actual.sql'
    schema = schema_path.read_text(encoding='utf-8')
    public_tables = re.findall(r'CREATE TABLE public\.(\w+)\s*\(', schema)
    db_doc = (DOCS / 'database-reference.md').read_text(encoding='utf-8')
    for table in public_tables:
        if f'### public.{table}\n' not in db_doc:
            errors.append(f'missing public table {table}')
        body = re.search(r'CREATE TABLE public\.' + table + r' \((.*?)\n\);', schema, re.S).group(1)
        section = db_doc.split(f'### public.{table}\n', 1)[1].split('\n### ', 1)[0]
        for field in re.findall(r'^    ([a-z][a-z0-9_]*) ', body, re.M):
            if f'| `{field}` |' not in section:
                errors.append(f'missing column {table}.{field}')
    adr = sorted((DOCS / 'decisions').glob('ADR-*.md'))
    if len(public_tables) != 35 or len(adr) != 16:
        errors.append('table/ADR count mismatch')
    frontend = frontend_inventory()
    version = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    result = {'version': version,
              'method': 'static source inspection; no pytest, vitest, Docker, DB or Ollama run',
              'markdown_files_checked': len(documents), 'local_links_checked': links,
              'public_tables': len(public_tables), 'adr': len(adr), 'model_sha256': actual_sha,
              'python_inventory': inventory, 'python_static_cases': sum(row['static_cases'] for row in inventory),
              'frontend_inventory': frontend, 'frontend_static_cases': sum(row['static_cases'] for row in frontend),
              'errors': errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
