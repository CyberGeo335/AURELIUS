from urllib.request import urlopen
from urllib.error import HTTPError

with urlopen('http://127.0.0.1:5173/', timeout=3) as response:
    assert response.status == 200 and b'<html' in response.read().lower()
try:
    urlopen('http://127.0.0.1:5173/api/v2/session', timeout=3)
except HTTPError as error:
    assert error.code == 401
else:
    raise RuntimeError('Expected unauthenticated session response')
