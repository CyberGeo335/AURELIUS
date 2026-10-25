"""Bounded document transport. Stored bytes are unverified evidence, never model inputs."""
import base64
import binascii
import csv
import hashlib
import io
import unicodedata

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_COLUMNS = "document_id,application_id,uploaded_by,data_request_id,filename,media_type,octet_length(content) AS size,sha256,source,processing_status,created_at"


def validate_document(filename: str, encoded: str) -> tuple[bytes, str]:
    from .cabinet import ApiError
    if (not isinstance(filename, str) or not 1 <= len(filename) <= 200
            or any(c in filename for c in '/\\')
            or any(unicodedata.category(c).startswith('C') for c in filename)):
        raise ApiError(400, "Недопустимое имя файла.")
    extension = filename.rsplit('.', 1)[-1].lower()
    if extension not in ('pdf', 'csv'):
        raise ApiError(400, "Допускаются только PDF и CSV.")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_DOCUMENT_BYTES + 2) // 3):
        raise ApiError(413, "Размер файла не должен превышать 10 МиБ.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ApiError(400, "Не удалось прочитать содержимое файла.")
    if not 0 < len(content) <= MAX_DOCUMENT_BYTES:
        raise ApiError(413, "Файл пуст или превышает 10 МиБ.")
    if extension == 'pdf':
        if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-1024:]:
            raise ApiError(400, "Файл не соответствует формату PDF.")
        return content, 'application/pdf'
    try:
        value = content.decode('utf-8-sig')
        if any(ord(c) < 32 and c not in '\r\n\t' for c in value):
            raise ValueError()
        # Validate transport syntax only. No values are imported or trusted.
        dialect = csv.Sniffer().sniff(value[:8192], delimiters=',;\t')
        reader = csv.reader(io.StringIO(value), dialect, strict=True)
        count = 0
        width = None
        for row in reader:
            if not row:
                continue
            width = width or len(row)
            if len(row) != width or width < 2:
                raise ValueError()
            count += 1
        if not count:
            raise ValueError()
    except (UnicodeError, ValueError, csv.Error):
        raise ApiError(400, "CSV должен быть в UTF-8 с одинаковым числом колонок и разделителем , ; или табуляцией.")
    return content, 'text/csv'


def store_document(db, user: dict, app: dict, body: dict) -> dict:
    from .cabinet import ApiError
    content, media_type = validate_document(body.get('filename'), body.get('content_base64'))
    request_id = body.get('data_request_id')
    if request_id is not None and not db.execute(
            "SELECT 1 FROM public.application_data_requests WHERE request_id=%s AND application_id=%s AND request_status='OPEN' FOR UPDATE",
            (request_id, app['application_id'])).fetchone():
        raise ApiError(409, "Открытый дозапрос этой заявки не найден.")
    result = db.execute(
        "INSERT INTO aurelius_cabinet.documents(application_id,uploaded_by,data_request_id,filename,media_type,content,sha256,source) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING document_id",
        (app['application_id'], user['user_id'], request_id, body['filename'], media_type, content,
         hashlib.sha256(content).hexdigest(), 'EMPLOYEE_UPLOAD' if user['role'] == 'BANK_EMPLOYEE' else 'CLIENT_UPLOAD')).fetchone()
    return {**result, 'filename': body['filename'], 'sha256': hashlib.sha256(content).hexdigest(),
            'data_request_id': request_id}
