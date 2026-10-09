"""issue #48：准备独立测试库 hormuz_sql_test（只读抽取 aisdb 判定走廊子集）。

- 绝不对 aisdb 执行任何写入；所有抽取都是 SELECT。
- 步骤：CREATE DATABASE（owner = 应用角色）→ 灌入真实表结构（pg_dump --schema-only）
  → COPY 走廊子集数据（ships / events / news / ais_import_batches 全量，
  ship_positions 仅判定走廊外扩范围）→ 016+017 迁移。
- 走廊子集覆盖通行判定与默认区域活动判定的全部读取范围
  （strait 判定带 25.8–27.1N × 55.8–57.1E；区域上下文再外扩 0.05°），
  因此语义等价于全库；v_data_coverage 的 coverage_scope 已注明该范围。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "hormuz_sql_test"
# 区域上下文外扩 0.05°，再留余量到 0.2°
LAT_MIN, LAT_MAX = 25.6, 27.3
LON_MIN, LON_MAX = 55.6, 57.3

TABLES_FULL = ["ships", "events", "news", "ais_import_batches"]
TABLES_SUBSET = ["ship_positions"]


def app_url(db_name: str) -> str:
    return (
        f"postgresql+psycopg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{db_name}"
    )


def admin_engine():
    return create_engine(app_url(os.environ["DB_NAME"]), isolation_level="AUTOCOMMIT")


def ensure_database() -> None:
    with admin_engine().connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB}
        ).scalar()
        if exists:
            conn.execute(text(f"DROP DATABASE {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB} OWNER {os.environ['DB_USER']}"))
    print(f"[prep] database {TEST_DB} created")


def load_schema() -> None:
    # ship_positions.location 依赖 PostGIS；扩展语句不在表过滤 dump 内，先显式创建。
    with create_engine(app_url(TEST_DB), isolation_level="AUTOCOMMIT").connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    dump = subprocess.run(
        [shutil_which("pg_dump"), "--schema-only", "--no-owner", "--no-privileges",
         "-h", os.environ["DB_HOST"], "-p", os.environ["DB_PORT"],
         "-U", os.environ["DB_USER"], "-d", os.environ["DB_NAME"],
         "-t", "ships", "-t", "ship_positions", "-t", "events", "-t", "news",
         "-t", "ais_import_batches"],
        capture_output=True, text=True, env={**os.environ, "PGPASSWORD": os.environ["DB_PASSWORD"]},
    )
    if dump.returncode != 0:
        raise SystemExit(f"[prep] pg_dump failed:\n{dump.stderr}")
    restore = subprocess.run(
        [shutil_which("psql"), "-v", "ON_ERROR_STOP=1",
         "-h", os.environ["DB_HOST"], "-p", os.environ["DB_PORT"],
         "-U", os.environ["DB_USER"], "-d", TEST_DB],
        input=dump.stdout, capture_output=True, text=True,
        env={**os.environ, "PGPASSWORD": os.environ["DB_PASSWORD"]},
    )
    if restore.returncode != 0:
        raise SystemExit(f"[prep] schema restore failed:\n{restore.stderr}")
    print("[prep] schema loaded")


def shutil_which(binary: str) -> str:
    import shutil
    candidates = [
        Path(r"D:\PostgreSQL\18\bin") / f"{binary}.exe",
        Path(r"C:\Program Files\PostgreSQL\18\bin") / f"{binary}.exe",
        Path(r"C:\Program Files\PostgreSQL\17\bin") / f"{binary}.exe",
        Path(r"C:\Program Files\PostgreSQL\16\bin") / f"{binary}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    path = shutil.which(binary)
    if not path:
        raise SystemExit(f"[prep] 找不到 {binary}，请先安装 PostgreSQL 客户端")
    return path


def copy_data() -> None:
    from sqlalchemy import MetaData, Table

    src = create_engine(app_url(os.environ["DB_NAME"]))
    dst = create_engine(app_url(TEST_DB))
    metadata = MetaData()
    with src.connect() as s, dst.begin() as d:
        for table in TABLES_FULL:
            rows = s.execute(text(f"SELECT * FROM {table}")).mappings().all()
            if not rows:
                continue
            target = Table(table, metadata, autoload_with=d)
            d.execute(target.insert(), [dict(r) for r in rows])
            print(f"[prep] {table}: {len(rows)} rows")

        cols = [c for c in s.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='ship_positions' ORDER BY ordinal_position"
        )).scalars() if c != "location"]
        select_cols = ", ".join(cols)
        count = s.execute(text(
            f"SELECT count(*) FROM ship_positions WHERE data_source='nnu_ais' "
            f"AND latitude BETWEEN {LAT_MIN} AND {LAT_MAX} "
            f"AND longitude BETWEEN {LON_MIN} AND {LON_MAX}"
        )).scalar()
        print(f"[prep] ship_positions subset: {count} rows, streaming...")
        result = s.execution_options(stream_results=True, yield_per=50_000).execute(
            text(f"SELECT {select_cols} FROM ship_positions WHERE data_source='nnu_ais' "
                 f"AND latitude BETWEEN {LAT_MIN} AND {LAT_MAX} "
                 f"AND longitude BETWEEN {LON_MIN} AND {LON_MAX} ORDER BY id")
        )
        target = Table("ship_positions", metadata, autoload_with=d)
        total = 0
        while True:
            batch = result.fetchmany(50_000)
            if not batch:
                break
            d.execute(target.insert(), [dict(zip(cols, row)) for row in batch])
            total += len(batch)
            print(f"[prep]   ... {total}/{count}")
        print(f"[prep] ship_positions: {total} rows copied")


def run_migration(filename: str) -> None:
    path = PROJECT_ROOT / "backend" / "sql" / filename
    run = subprocess.run(
        [shutil_which("psql"), "-v", "ON_ERROR_STOP=1",
         "-h", os.environ["DB_HOST"], "-p", os.environ["DB_PORT"],
         "-U", os.environ["DB_USER"], "-d", TEST_DB, "-f", str(path)],
        capture_output=True, text=True, env={**os.environ, "PGPASSWORD": os.environ["DB_PASSWORD"]},
    )
    if run.returncode != 0:
        raise SystemExit(f"[prep] {filename} failed:\n{run.stderr}")
    print(f"[prep] {filename} applied")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    started = time.time()
    ensure_database()
    load_schema()
    copy_data()
    run_migration("016_agent_views_nnu_ais.sql")
    run_migration("017_agent_analysis_snapshots.sql")
    with create_engine(app_url(TEST_DB)).connect() as conn:
        print("positions:", conn.execute(text("SELECT count(*) FROM ship_positions")).scalar())
        print("agent_data rels:", conn.execute(text(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='agent_data' ORDER BY 1")).all())
    print(f"[prep] done in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
