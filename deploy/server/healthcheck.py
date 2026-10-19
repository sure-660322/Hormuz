import urllib.request
from sqlalchemy import text
from backend.app.database import engine

with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
    assert response.status == 200
with engine.connect() as connection:
    assert connection.execute(text("SELECT EXISTS(SELECT FROM ships)")).scalar()
