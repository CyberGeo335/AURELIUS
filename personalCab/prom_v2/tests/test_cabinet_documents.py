import base64

import pytest

from personalCab.prom_v2.cabinet import ApiError
from personalCab.prom_v2.cabinet_documents import MAX_DOCUMENT_BYTES, validate_document


@pytest.mark.parametrize('filename,content,media', [
    ('отчёт.PDF', b'%PDF-1.4\nfixture\n%%EOF\n', 'application/pdf'),
    ('statement.csv', 'месяц;сумма\n2026-09;100\n'.encode(), 'text/csv'),
])
def test_document_format_validation(filename, content, media):
    assert validate_document(filename, base64.b64encode(content).decode()) == (content, media)


@pytest.mark.parametrize('filename,content', [
    ('../a.pdf', b'%PDF-1.4\n%%EOF'), ('a.exe', b'abc'), ('a.pdf', b'fake'),
    ('a.csv', b'\xff\x00'), ('a.csv', b'a,b\n1,2,3'), ('a.csv', b''),
    ('a\n.pdf', b'%PDF-1.4\n%%EOF'), ('a.csv', b'a,b\n1,\x00'),
])
def test_document_rejects_invalid_format(filename, content):
    with pytest.raises(ApiError):
        validate_document(filename, base64.b64encode(content).decode())


def test_document_rejects_bad_encoding_and_oversize():
    for encoded in ('not base64!', 'A' * (4 * ((MAX_DOCUMENT_BYTES + 2) // 3) + 4)):
        with pytest.raises(ApiError):
            validate_document('file.pdf', encoded)
