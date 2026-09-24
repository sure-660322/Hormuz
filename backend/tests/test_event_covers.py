"""事件封面通过事件编号读取；图片根目录可配置且不可越界。"""

from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app


class FakeCoverDb:
    image_path: str | None = None

    def scalar(self, _statement):
        return self.image_path


def test_event_cover_serves_configured_image_and_rejects_unsafe_paths(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    cover = images / "cover.jpg"
    cover.write_bytes(b"\xff\xd8\xff\xd9")
    monkeypatch.setenv("NEWS_IMAGE_ROOT", str(tmp_path))
    db = FakeCoverDb()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            db.image_path = "images/cover.jpg"
            response = client.get("/events/evt_001/cover")
            assert response.status_code == 200
            assert response.content == cover.read_bytes()
            assert response.headers["content-type"] == "image/jpeg"
            assert response.headers["cache-control"] == "public, max-age=3600"

            for image_path in (None, "images/missing.jpg", "images/../secret.jpg", str(cover)):
                db.image_path = image_path
                assert client.get("/events/evt_001/cover").status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
