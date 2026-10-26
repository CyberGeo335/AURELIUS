"""Build both driver URLs from one source without logging credentials."""
import os
import sys
from urllib.parse import quote

if 'PG_PASSWORD' in os.environ and not os.environ['PG_PASSWORD'].strip():
    raise SystemExit('PG_PASSWORD must be nonempty; set POSTGRES_PASSWORD in .env')

if os.getenv('PG_PASSWORD'):
    user = quote(os.environ['PG_USER'], safe='')
    password = quote(os.environ['PG_PASSWORD'], safe='')
    database = quote(os.environ['PG_DATABASE'], safe='')
    authority = f"{user}:{password}@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{database}"
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://' + authority
    os.environ['AURELIUS_DATABASE_URL'] = 'postgresql://' + authority
os.execvp(sys.argv[1], sys.argv[1:])
