"""Reviewed news entries are database-backed and fail closed on incomplete evidence."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.case_news_data import ARTICLES, CASE_NEWS, event_key, story_id


def fake_db(*, missing=None, altered=False):
    events = [SimpleNamespace(event_id=spec["event_id"], event_key=event_key(key) if not altered else "wrong",
                              story_ids=[story_id(s) for s in spec["sources"]], title_zh=spec["title"], summary_zh=spec["summary"])
              for key, spec in CASE_NEWS.items()]
    stories = [SimpleNamespace(story_id=story_id(key), title_zh=a["title_zh"], media_name=a["media"],
                               publish_date=date.fromisoformat(a["date"]), canonical_url=a["url"], summary_zh=a["summary_zh"])
               for key, a in ARTICLES.items() if key != missing]

    class DB:
        def __init__(self):
            self.results = iter([events, stories])

        def scalars(self, query):
            self.rows = next(self.results)
            return self

        def all(self):
            return self.rows

    return DB()


@pytest.mark.parametrize("missing,altered", [(None, False), ("baird", False), (None, True)])
def test_news_catalog_identity_and_evidence_gate(missing, altered):
    from backend.app.database import get_db
    from backend.app.main import app
    app.dependency_overrides[get_db] = lambda: fake_db(missing=missing, altered=altered)
    try:
        response = TestClient(app).get("/cases/news-entries")
        assert response.status_code == 200
        entries = response.json()
        assert len(entries) == 4
        for entry in entries:
            spec = CASE_NEWS[entry["case_id"]]
            ready = not altered and missing not in spec["sources"]
            assert entry["available"] == ready
            assert entry["mmsi"] == spec["mmsi"] and entry["imo"] == spec["imo"]
            assert any('\u4e00' <= c <= '\u9fff' for c in entry["title_zh"])
            assert len(entry["articles"]) == (len(spec["sources"]) if ready else 0)
            assert all(a["url"].startswith("https://") for a in entry["articles"])
    finally:
        app.dependency_overrides.clear()


def test_shared_original_is_not_a_duplicate_story():
    assert "baird" in CASE_NEWS["mraikh"]["sources"]
    assert "baird" in CASE_NEWS["tong-lin-wan"]["sources"]
    assert len({story_id(s) for c in CASE_NEWS.values() for s in c["sources"]}) == 5
