"""Back up and atomically replace events/news with the approved step3 dataset.

Run from project root: python -m backend.migrate_real_news [--apply]
Credentials are consumed by the existing connection module, never printed.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from sqlalchemy import inspect, select, text
from backend.app.database import engine
from backend.app.models import Event, News

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(r"D:\my_project\news_raw_data")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_rows(name, table):
    path = DATA / f"{name}_step3_20260226_20260302.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    for row in rows:
        row.pop("content", None)
        require(set(row) == set(table.columns.keys()) - {"id"}, f"Unexpected {name} fields")
        for column in table.columns:
            if column.name == "id":
                continue
            value = row[column.name]
            require(column.nullable or value is not None, f"Null {name}.{column.name}")
            if value is None:
                continue
            if column.name == "event_datetime":
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                # Date-only values are storage placeholders, not precise event times.
                row[column.name] = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            elif column.name.startswith("publish_date"):
                row[column.name] = date.fromisoformat(value)
            elif column.name in {"event_points", "perspectives", "story_ids", "mentioned_vessels"}:
                require(isinstance(value, list), f"Expected array: {column.name}")
            elif isinstance(value, str) and getattr(column.type, "length", None):
                require(len(value) <= column.type.length, f"Too long: {column.name}")
        lat, lng = row["event_lat"], row["event_lng"]
        require((lat is None) == (lng is None), "Incomplete coordinates")
        require(lat is None or (-90 <= lat <= 90 and -180 <= lng <= 180), "Invalid coordinates")
    return rows, hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(c, table):
    return tuple(c.execute(text(f"SELECT count(*), md5(string_agg(row_to_json(t)::text, '' ORDER BY id)) FROM public.{table} t")).one())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    events, eh = read_rows("events", Event.__table__)
    news, nh = read_rows("news", News.__table__)
    require((len(events), len(news)) == (65, 290), "Unexpected input counts")
    for rows, keys in [(events, ["event_id", "event_key"]), (news, ["story_id", "canonical_url"])]:
        for key in keys:
            require(len({r[key] for r in rows}) == len(rows), f"Duplicate {key}")
    ids = {r["event_id"] for r in events}
    for n in news:
        require(type(n["relevant"]) is bool, "Invalid relevant flag")
        if not n["relevant"]:
            n["event_id"] = None
        require(n["event_id"] in ids if n["relevant"] else n["event_id"] is None, "Unmapped event")
    counts = Counter(n["event_id"] for n in news)
    require(counts[None] == 67, "Unexpected unlinked count")
    for e in events:
        linked = {n["story_id"] for n in news if n["event_id"] == e["event_id"]}
        require(linked == set(e["story_ids"]) and len(linked) == e["coverage_count"], "Coverage mismatch")
    print("Input validated: events=65 news=290 linked=223 unlinked=67")
    if not args.apply:
        return
    backup = ROOT / "data" / "db_backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup.mkdir(parents=True)
    with engine.begin() as c:
        c.execute(text("SET LOCAL lock_timeout = '10s'"))
        c.execute(text("SET LOCAL search_path = public"))
        tables = [t for t in ["events", "news"] if inspect(c).has_table(t, schema="public")]
        c.execute(text("LOCK TABLE " + ", ".join(tables + ["ships", "ship_positions"]) + " IN SHARE MODE"))
        before = {t: fingerprint(c, t) for t in ["ships", "ship_positions"]}
        old_counts = {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables}
        # Use this engine's exact endpoint; supply the password only via subprocess stdin.
        url = engine.url
        require(url.host in {"127.0.0.1", "localhost"} and url.port == 25432, "Unexpected DB endpoint")
        command = ["docker", "exec", "-i", "mobilitydb", "sh", "-c",
                   'IFS= read -r PGPASSWORD; export PGPASSWORD; exec "$@"', "sh",
                   "pg_dump", "-h", "127.0.0.1", "-U", url.username, "-d", url.database,
                   "-Fc", "--no-owner", "--no-privileges"]
        for t in tables:
            command.extend(["-t", f"public.{t}"])
        archive = backup / "events_news.dump"
        with archive.open("wb") as output:
            subprocess.run(command, input=(url.password + "\n").encode(), stdout=output, check=True)
        with archive.open("rb") as source:
            listing = subprocess.run(["docker", "exec", "-i", "mobilitydb", "pg_restore", "--list"], stdin=source, capture_output=True, check=True).stdout.decode()
        require(all(f"TABLE DATA public {t} " in listing for t in tables), "Incomplete backup archive")
        (backup / "archive_list.txt").write_text(listing, encoding="utf-8")
        (backup / "manifest.json").write_text(json.dumps({"old_counts": old_counts, "ships_before": before,
            "input_sha256": {"events": eh, "news": nh}, "backup_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
        print(f"Backup verified: {archive}; old counts={old_counts}")
        ddl = (ROOT / "backend/sql/006_rebuild_events_create_news.sql").read_text(encoding="utf-8")
        c.exec_driver_sql(ddl)
        c.execute(Event.__table__.insert(), events)
        mapping = dict(c.execute(select(Event.event_id, Event.id)).all())
        for n in news:
            n["event_id"] = mapping[n["event_id"]] if n["event_id"] else None
        c.execute(News.__table__.insert(), news)
        result = tuple(c.execute(text("SELECT (SELECT count(*) FROM events), count(*), count(event_id), count(*) FILTER (WHERE event_id IS NULL) FROM news")).one())
        require(result == (65, 290, 223, 67), "Import count mismatch")
        for t in before:
            require(fingerprint(c, t) == before[t], f"{t} changed")
        for table in [Event.__table__, News.__table__]:
            actual = inspect(c).get_columns(table.name, schema="public")
            require({x['name']: x['nullable'] for x in actual} == {x.name: x.nullable for x in table.columns}, "Column mismatch")
            stored = c.execute(select(table).order_by(table.c.id)).mappings().all()
            expected = events if table.name == 'events' else news
            require([{k: v for k, v in r.items() if k != 'id'} for r in stored] == expected, "Stored values differ")
        print("Verified all stored fields, schema nullability, counts and unchanged ship tables:", result)
    print("COMMITTED")


if __name__ == "__main__":
    main()
