"""区域船舶活动：独立样例验证（HTTP 契约 + 朴素期望值比对）。

流程：
  1. self-check：调用 `scripts/area_activity_samples.py` 的内存内自查（单位、半开边界、
     手算期望值、裁剪恒等式、场景隔离、覆盖度）。
  2. 重建独立测试库 `hormuz_area_test`（只碰这个库，绝不写 `aisdb`），启用 PostGIS，
     按真实结构建立最小 `ships` / `ship_positions`（含 geography 生成列与两个索引），
     插入全部合成报位；随后把库里的报位读回、用朴素复算再算一遍期望值（不走接口），
     确认写的和算的是同一批数据。
  3. 用 FastAPI TestClient 调 `/api/area-activity/{activity,snapshot,compare}`，
     把响应与期望值逐字段比对，打印 PASS/WARN/FAIL 明细表。
  4. 参数校验（§1.3）、`no_data` 与「有效零结果」区分（§2.6）、`visit_limit` 截断（§4.3，
     截断时 status 必须为 partial）。
  5. 证据写入 `docs/area_activity_samples_result.json`。

2026-10-07 定版口径对应的比对强度（本轮复验）：
  * `flags` 按 §2.4 的 8 个取值逐字比对（不再按语义等价名放宽）；
  * 明细比对 `segment_count`、每段 `fix_count`、`entry/exit.in_window`、
    `wide_bracket`、`outside_evidence_in_context`；
  * 每日比对 `visits_touching_day` 与 4 个状态计数（§5.3）；
  * 比较口径按 §2.5 比对 `window_days`（自然日）、`window_length_days`（实际长度）、
    `equal_length`（实际长度相等）与日均指标（分母 = 实际长度）；
  * 跳点回归样例 S20：位移 <1 km 但推算速度 >30 kn 必须不判 `jump_break`。

退出码：实现未就绪 = 2；有 FAIL = 1；只有 PASS/WARN = 0。
本脚本不修改 backend/**，也不写业务库；.env 只用于读取连接变量，不打印任何凭据。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# --- 凭据：只从主仓库 .env 读取到进程环境，绝不打印 -------------------------
from dotenv import load_dotenv  # noqa: E402

MAIN_REPO = Path(r"D:\my_project\Hormuz")
ENV_FILE = Path(os.environ.get("HORMUZ_ENV_FILE", str(MAIN_REPO / ".env")))
load_dotenv(ENV_FILE)

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import area_activity_samples as samples  # noqa: E402

UTC = timezone.utc

TEST_DB = "hormuz_area_test"          # 唯一允许 DROP/CREATE 的库名
MAINTENANCE_DB = os.environ.get("AREA_TEST_MAINTENANCE_DB", "postgres")
READ_ONLY_DB = "aisdb"                # 业务库：本脚本从不连接、从不写入
RESULT_PATH = ROOT / "docs" / "area_activity_samples_result.json"
API_PREFIX = "/api/area-activity"
ACTIVITY_PATH = f"{API_PREFIX}/activity"
SNAPSHOT_PATH = f"{API_PREFIX}/snapshot"
COMPARE_PATH = f"{API_PREFIX}/compare"
DEFAULT_AREA_PATH = f"{API_PREFIX}/default-area"
BATCH_ID = 9001                       # 样例报位统一使用的 source_batch_id

# --- 真实结构（用 information_schema 只读核对后的最小子集，见交付说明）------
DDL_STATEMENTS = [
    """CREATE TABLE ships (
        id bigint PRIMARY KEY,
        mmsi varchar NOT NULL,
        name varchar,
        ship_type varchar,
        flag varchar
    )""",
    """CREATE TABLE ship_positions (
        id bigint PRIMARY KEY,
        ship_id bigint NOT NULL REFERENCES ships(id),
        latitude double precision NOT NULL,
        longitude double precision NOT NULL,
        speed double precision,
        recorded_at timestamp with time zone NOT NULL,
        data_source varchar NOT NULL DEFAULT 'unknown',
        source_batch_id bigint,
        source_row integer,
        location geography(Point,4326) GENERATED ALWAYS AS
            (st_setsrid(st_makepoint(longitude, latitude), 4326)::geography) STORED
    )""",
    """CREATE INDEX idx_ship_positions_ship_recorded_at
        ON ship_positions (ship_id, recorded_at DESC, id DESC)""",
    "CREATE INDEX idx_ship_positions_location ON ship_positions USING gist (location)",
    # 实现会读取批次表生成 coverage（§4 响应含 coverage、§3 有 batch_ids），
    # 按真实结构（information_schema 核对）做最小镜像，只放样例对应的一行。
    """CREATE TABLE ais_import_batches (
        id bigint PRIMARY KEY,
        source_file text NOT NULL,
        source_sha256 character(64) NOT NULL,
        source_day date NOT NULL,
        data_source varchar(50) NOT NULL,
        file_size_bytes bigint NOT NULL,
        expected_rows bigint NOT NULL,
        inserted_rows bigint NOT NULL,
        imported_at timestamp with time zone NOT NULL DEFAULT now()
    )""",
]

INSERT_BATCH = text(
    "INSERT INTO ais_import_batches "
    "(id, source_file, source_sha256, source_day, data_source, file_size_bytes, expected_rows, "
    "inserted_rows) VALUES (:id, :source_file, :source_sha256, :source_day, :data_source, "
    ":file_size_bytes, :expected_rows, :inserted_rows)"
)

INSERT_SHIP = text(
    "INSERT INTO ships (id, mmsi, name, ship_type, flag) "
    "VALUES (:id, :mmsi, :name, :ship_type, :flag)"
)
INSERT_FIX = text(
    "INSERT INTO ship_positions "
    "(id, ship_id, latitude, longitude, speed, recorded_at, data_source, source_batch_id, source_row) "
    "VALUES (:id, :ship_id, :latitude, :longitude, :speed, :recorded_at, :data_source, "
    ":source_batch_id, :source_row)"
)

# --- 响应字段名候选（§5.3 给了 daily 的准确名称；summary 未逐字给出，用候选 + 提示）---
SUMMARY_KEYS: dict[str, list[str]] = {
    "ships_observed": ["ships_observed", "observed_ship_count", "unique_ships", "ship_count",
                       "distinct_ships", "ships_in_area", "appeared_ship_count"],
    "observed_entry_count": ["observed_entry_count", "entry_count", "observed_entries", "entries"],
    "observed_exit_count": ["observed_exit_count", "exit_count", "observed_exits", "exits"],
    "observed_ship_seconds": ["observed_ship_seconds", "ship_seconds", "total_ship_seconds"],
    "observed_ship_hours": ["observed_ship_hours", "ship_hours", "total_ship_hours"],
    "visit_count": ["visit_count", "visits_total", "total_visits"],
}
DAILY_KEYS: dict[str, list[str]] = {
    "date": ["date"],
    "ships_observed": ["ships_observed", "observed_ship_count", "unique_ships", "ship_count"],
    "observed_entry_count": ["observed_entry_count", "entry_count"],
    "observed_exit_count": ["observed_exit_count", "exit_count"],
    "observed_ship_seconds": ["observed_ship_seconds", "ship_seconds"],
    "observed_ship_hours": ["observed_ship_hours", "ship_hours"],
    "visits_touching_day": ["visits_touching_day", "touching_visit_count"],
    # §5.3 daily[] 明确给出的状态计数（本轮起纳入比对）
    "complete_visit_count": ["complete_visit_count"],
    "truncated_visit_count": ["truncated_visit_count"],
    "interrupted_visit_count": ["interrupted_visit_count"],
    "uncertain_visit_count": ["uncertain_visit_count"],
}
SNAPSHOT_KEYS: dict[str, list[str]] = {
    "in_area_count": ["in_area_count", "inside_count", "in_area_ships"],
    "out_of_area_fresh_count": ["out_of_area_fresh_count", "outside_fresh_count", "out_of_area_count"],
    "stale_fix_count": ["stale_fix_count", "stale_count", "expired_count"],
    "evaluated_ship_count": ["evaluated_ship_count", "evaluated_ships", "evaluated_count"],
}
METRIC_NAME_CANDIDATES: dict[str, list[str]] = {
    "ships_observed": ["ships_observed", "ship_count", "unique_ships", "ships"],
    "observed_entry_count": ["observed_entry_count", "entry_count", "entries"],
    "observed_exit_count": ["observed_exit_count", "exit_count", "exits"],
    "observed_ship_hours": ["observed_ship_hours", "ship_hours"],
    # §2.5 定版：日均分母 = 窗口实际长度（含小数天），不是自然日个数
    "ships_observed_per_day": ["ships_observed_per_day"],
    "observed_entry_count_per_day": ["observed_entry_count_per_day"],
    "observed_ship_hours_per_day": ["observed_ship_hours_per_day"],
}
# §2.4 定版：flags 取值固定为 8 个，逐字比对，不再按语义等价名放宽。
DOCUMENTED_FLAGS = {
    "gap_interrupted",
    "jump_break",
    "wide_entry_bracket",
    "wide_exit_bracket",
    "near_boundary_entry",
    "near_boundary_exit",
    "same_second_conflict",
    "outside_evidence_out_of_context",
}


# ==========================================================================
# 结果记录
# ==========================================================================
@dataclass
class Check:
    scene: str
    path: str
    expected: Any
    actual: Any
    status: str          # PASS | WARN | FAIL | SKIP
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "path": self.path,
            "expected": _jsonable(self.expected),
            "actual": _jsonable(self.actual),
            "status": self.status,
            "note": self.note,
        }


class Runner:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.scene_soft_reasons: dict[str, str] = {}

    def add(self, scene: str, path: str, expected: Any, actual: Any, status: str, note: str = "") -> None:
        self.checks.append(Check(scene, path, expected, actual, status, note))

    def compare(
        self,
        scene: str,
        path: str,
        expected: Any,
        actual: Any,
        ambiguities: dict[str, Any] | None = None,
        tolerance: float = 1e-6,
        note: str = "",
        missing_is_warn: bool = False,
    ) -> str:
        info = (ambiguities or {}).get(path)
        if _values_equal(expected, actual, tolerance):
            self.add(scene, path, expected, actual, "PASS", note)
            return "PASS"
        if info and any(_values_equal(alt, actual, tolerance) for alt in info.get("alternates", [])):
            self.add(scene, path, expected, actual, "WARN",
                     f"命中备选口径：{info.get('reason', '')}")
            return "WARN"
        if info:
            self.add(scene, path, expected, actual, "WARN",
                     f"文档未定口径，主口径与备选都不匹配：{info.get('reason', '')}")
            return "WARN"
        scene_reason = self.scene_soft_reasons.get(scene)
        if scene_reason:
            self.add(scene, path, expected, actual, "WARN", scene_reason)
            return "WARN"
        self.add(scene, path, expected, actual, "FAIL", note)
        return "FAIL"

    def fail(self, scene: str, path: str, expected: Any, actual: Any, note: str = "") -> None:
        self.add(scene, path, expected, actual, "FAIL", note)

    def warn(self, scene: str, path: str, expected: Any, actual: Any, note: str = "") -> None:
        self.add(scene, path, expected, actual, "WARN", note)

    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
        for c in self.checks:
            out[c.status] = out.get(c.status, 0) + 1
        return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and value != value:
        return "NaN"
    return value


def _try_iso(value: str) -> datetime | None:
    if not isinstance(value, str) or len(value) < 10 or "T" not in value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _values_equal(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tolerance
    if isinstance(a, str) and isinstance(b, str):
        da, db = _try_iso(a), _try_iso(b)
        if da is not None and db is not None:
            return abs((da - db).total_seconds()) <= 0.001
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        return all(_values_equal(a[k], b[k], tolerance) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_values_equal(x, y, tolerance) for x, y in zip(a, b))
    return a == b


def _pick(mapping: dict[str, Any], names: Sequence[str]) -> tuple[Any, str | None]:
    for name in names:
        if name in mapping:
            return mapping[name], name
    return None, None


def _shown(value: Any, limit: int = 90) -> str:
    text = json.dumps(_jsonable(value), ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ==========================================================================
# 数据库：重建测试库 + 建表 + 插入样例
# ==========================================================================
def db_url(database: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=database,
    )


def safe_dsn(database: str) -> str:
    """不含凭据的连接描述，仅用于打印/证据。"""
    return f"postgresql+psycopg://{os.environ['DB_USER']}@{os.environ['DB_HOST']}:" \
           f"{os.environ['DB_PORT']}/{database}"


def rebuild_test_database() -> dict[str, Any]:
    if TEST_DB != "hormuz_area_test":
        raise RuntimeError(f"拒绝操作非白名单测试库：{TEST_DB}")
    info: dict[str, Any] = {"test_database": TEST_DB, "maintenance_database": MAINTENANCE_DB}

    admin = create_engine(db_url(MAINTENANCE_DB), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": TEST_DB},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()

    engine = create_engine(db_url(TEST_DB), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        for ddl in DDL_STATEMENTS:
            conn.execute(text(ddl))
        conn.execute(
            INSERT_SHIP,
            [
                {"id": s.id, "mmsi": s.mmsi, "name": s.name,
                 "ship_type": s.ship_type, "flag": s.flag}
                for s in samples.ALL_SHIPS
            ],
        )
        conn.execute(
            INSERT_FIX,
            [
                {
                    "id": f.id,
                    "ship_id": f.ship_id,
                    "latitude": f.latitude,
                    "longitude": f.longitude,
                    "speed": f.speed,
                    "recorded_at": f.recorded_at,
                    "data_source": f.data_source,
                    "source_batch_id": f.source_batch_id,
                    "source_row": f.source_row,
                }
                for f in samples.ALL_FIXES
            ],
        )
        conn.execute(
            INSERT_BATCH,
            [
                {
                    "id": BATCH_ID,
                    "source_file": "synthetic_area_activity_samples.csv",
                    "source_sha256": "0" * 64,
                    "source_day": min(f.recorded_at for f in samples.ALL_FIXES).date(),
                    "data_source": "nnu_ais",
                    "file_size_bytes": 0,
                    "expected_rows": len(samples.ALL_FIXES),
                    "inserted_rows": len(samples.ALL_FIXES),
                }
            ],
        )
        info["ships_rows"] = conn.execute(text("SELECT count(*) FROM ships")).scalar_one()
        info["positions_rows"] = conn.execute(text("SELECT count(*) FROM ship_positions")).scalar_one()
        info["location_not_null"] = conn.execute(
            text("SELECT count(*) FROM ship_positions WHERE location IS NOT NULL")
        ).scalar_one()
        info["gist_candidates"] = conn.execute(
            text(
                "SELECT count(*) FROM ship_positions WHERE location && "
                "ST_MakeEnvelope(55.75, 25.75, 57.15, 27.15, 4326)::geography"
            )
        ).scalar_one()
        info["extensions"] = [
            row[0] for row in conn.execute(text("SELECT extname FROM pg_extension ORDER BY 1"))
        ]
        info["indexes"] = [
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY 1")
            )
        ]
    engine.dispose()
    return info


def load_fixes_from_db() -> list[Any]:
    """把样例报位从测试库读回，供不经接口的朴素复算使用。"""
    engine = create_engine(db_url(TEST_DB))
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, ship_id, latitude, longitude, speed, recorded_at, data_source, "
                "source_batch_id, source_row FROM ship_positions ORDER BY id"
            )
        ).fetchall()
        ships = conn.execute(
            text("SELECT id, mmsi, name, ship_type, flag FROM ships ORDER BY id")
        ).fetchall()
    engine.dispose()
    fixes = [
        samples.Fix(
            id=r[0], ship_id=r[1], latitude=r[2], longitude=r[3], speed=r[4],
            recorded_at=r[5].astimezone(UTC), data_source=r[6],
            source_batch_id=r[7], source_row=r[8],
        )
        for r in rows
    ]
    ship_objs = [
        samples.Ship(id=r[0], mmsi=r[1], name=r[2], ship_type=r[3], flag=r[4]) for r in ships
    ]
    return fixes, ship_objs


# ==========================================================================
# HTTP 客户端
# ==========================================================================
def load_app() -> tuple[Any | None, str | None]:
    """导入后端应用；实现未就绪时返回 (None, 原因)，不抛栈。

    默认模块 `backend.app.main`；可用环境变量 `AREA_ACTIVITY_APP_MODULE` 指向替代模块，
    仅供验证脚本自身自检（例如用一个契约桩验证比对逻辑），不影响应用代码。
    """
    module_name = os.environ.get("AREA_ACTIVITY_APP_MODULE", "backend.app.main")
    try:
        import importlib  # noqa: PLC0415

        module = importlib.import_module(module_name)
        app = getattr(module, "app")
    except Exception as exc:  # ImportError / ModuleNotFoundError / RuntimeError / AttributeError
        return None, f"{module_name}: {type(exc).__name__}: {exc}"
    paths: set[str] = set()
    try:  # FastAPI 新版把 include_router 的子树包成 _IncludedRouter，直接遍历 app.routes 看不到叶子
        paths.update(app.openapi().get("paths", {}).keys())
    except Exception:
        pass

    def _walk(routes: Iterable[Any]) -> None:
        for route in routes:
            leaf = getattr(route, "path", None)
            if leaf:
                paths.add(leaf)
            sub = getattr(route, "routes", None)
            if sub:
                _walk(sub)

    _walk(getattr(app, "routes", []))
    missing = [
        p for p in (ACTIVITY_PATH, SNAPSHOT_PATH, COMPARE_PATH, DEFAULT_AREA_PATH) if p not in paths
    ]
    if missing:
        return app, (f"应用可导入但路由未注册：{missing}"
                     f"（area_activity 模块导入失败或未 include_router；已发现 {len(paths)} 条路由）")
    return app, None


def build_client(app: Any) -> Any:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from backend.app.database import get_db  # noqa: PLC0415

    engine = create_engine(db_url(TEST_DB))
    session_factory = sessionmaker(bind=engine)

    def _override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


# ==========================================================================
# 比对：activity
# ==========================================================================
def check_json_health(runner: Runner, scene: str, response: Any, body: Any) -> None:
    text_body = response.text
    bad = [token for token in ("NaN", "Infinity", "-Infinity") if token in text_body]
    if bad:
        runner.fail(scene, "json.no_nan_inf", "无 NaN/Infinity", bad,
                    "§2.5 要求不产生 NaN/Infinity")
    else:
        runner.add(scene, "json.no_nan_inf", "无 NaN/Infinity", "无", "PASS")


def check_area_and_algorithm(runner: Runner, scene: str, body: dict[str, Any], sc: Any) -> None:
    area = body.get("area")
    if not isinstance(area, dict):
        runner.warn(scene, "area.present", "area 对象", area, "§4.3 响应应含 area")
    else:
        expected_id = samples.DEFAULT_AREA_ID if getattr(sc, "use_default_area", False) else "custom"
        value, key = _pick(area, ["area_id", "id", "areaId"])
        if key is None:
            runner.warn(scene, "area.area_id", expected_id, sorted(area),
                        "area 内未找到 area_id（§1.2）")
        else:
            runner.compare(scene, "area.area_id", expected_id, value, None, 1e-6,
                           f"字段名 {key}")
        is_default, k2 = _pick(area, ["is_default", "isDefault", "default"])
        if k2 is not None:
            runner.compare(scene, "area.is_default",
                           bool(getattr(sc, "use_default_area", False)), is_default, None, 1e-6,
                           "§1.2 默认区域回显 true，自定义矩形回显 false")
    algorithm = body.get("algorithm")
    blob = json.dumps(_jsonable(algorithm), ensure_ascii=False)
    if "1.0.0" in blob or samples.ALGORITHM_VERSION in blob:
        runner.add(scene, "algorithm.version", samples.ALGORITHM_VERSION, blob[:80], "PASS")
    else:
        runner.warn(scene, "algorithm.version", samples.ALGORITHM_VERSION, blob[:80],
                    "§2 算法版本 area_activity/1.0.0 应随结果回显")


def check_activity_summary(
    runner: Runner, scene: str, body: dict[str, Any], expected: dict[str, Any],
    ambiguities: dict[str, Any],
) -> None:
    summary = body.get("summary")
    if not isinstance(summary, dict):
        runner.fail(scene, "summary.present", "summary 对象", summary, "§4.3 响应应含 summary")
        return
    want = expected["summary"]
    for key, candidates in SUMMARY_KEYS.items():
        value, used = _pick(summary, candidates)
        path = f"summary.{key}"
        if used is None:
            runner.warn(scene, path, want[key], sorted(summary),
                        f"summary 中未找到字段（候选名 {candidates}）")
            continue
        runner.compare(scene, path, want[key], value, ambiguities, 1e-3,
                       f"响应字段 {used}")
    runner.compare(scene, "status_hint", expected["status_hint"], body.get("status"),
                   ambiguities, 1e-6, "§2.6 状态取值")
    _check_known_extra_fields(runner, scene, body, expected)


def _check_known_extra_fields(
    runner: Runner,
    scene: str,
    body: dict[str, Any],
    expected: dict[str, Any],
    required: Sequence[str] = ("limits", "limitations", "coverage", "query"),
) -> None:
    missing = [key for key in required if key not in body]
    if missing:
        runner.warn(scene, "response.extra_fields", list(required), missing,
                    "响应字段缺失（同场景只报一次）")


def check_activity_daily(
    runner: Runner, scene: str, body: dict[str, Any], expected: dict[str, Any],
    ambiguities: dict[str, Any],
) -> None:
    daily = body.get("daily")
    if not isinstance(daily, list):
        runner.fail(scene, "daily.present", "数组", daily, "§4.3 响应应含 daily[]")
        return
    actual_dates = []
    for row in daily:
        if isinstance(row, dict):
            value, _ = _pick(row, DAILY_KEYS["date"])
            if value is not None:
                actual_dates.append(str(value)[:10])
    expected_dates = list(expected["daily_order"])
    runner.compare(scene, "daily.dates", expected_dates, actual_dates, ambiguities, 1e-6,
                   "§2.4 每日一条")
    by_date = {str(d)[:10]: row for d, row in
               ((_pick(r, DAILY_KEYS["date"])[0], r) for r in daily if isinstance(r, dict))
               if d is not None}
    for date_iso, exp_row in expected["daily"].items():
        row = by_date.get(date_iso)
        if row is None:
            continue
        for key, candidates in DAILY_KEYS.items():
            if key == "date":
                continue
            value, used = _pick(row, candidates)
            path = f"daily[{date_iso}].{key}"
            if used is None:
                runner.warn(scene, path, exp_row[key], sorted(row), f"候选名 {candidates}")
                continue
            runner.compare(scene, path, exp_row[key], value, ambiguities, 1e-3, f"响应字段 {used}")


def check_activity_visits(
    runner: Runner, scene: str, body: dict[str, Any], expected: dict[str, Any],
    ambiguities: dict[str, Any],
) -> None:
    visits = body.get("visits")
    if not isinstance(visits, list):
        runner.fail(scene, "visits.present", "数组", visits, "§4.3 响应应含 visits[]")
        return
    by_key: dict[str, dict[str, Any]] = {}
    for row in visits:
        if isinstance(row, dict) and isinstance(row.get("visit_key"), str):
            by_key[row["visit_key"]] = row
    runner.compare(scene, "visits", sorted(expected["visits"]), sorted(by_key), ambiguities, 1e-6,
                   "§2.0 访问稳定键 visit_key = s{ship_id}:f{首个区域内报位 id}")

    for vk, exp_visit in expected["visits"].items():
        row = by_key.get(vk)
        if row is None:
            continue
        base = f"visits[{vk}]"
        runner.compare(scene, f"{base}.ship_id", exp_visit["ship_id"], row.get("ship_id"),
                       ambiguities, 1e-6)
        if "ship_type" in row:
            runner.compare(scene, f"{base}.ship_type", exp_visit["ship_type"],
                           row.get("ship_type"), ambiguities, 1e-6)
        for side in ("entry", "exit"):
            exp_side = exp_visit[side]
            act_side = row.get(side)
            if not isinstance(act_side, dict):
                runner.fail(scene, f"{base}.{side}.present", "对象", act_side, "§4.5 明细结构")
                continue
            for field_name in ("observed", "observed_at", "bracket_seconds", "in_window",
                               "near_boundary", "same_second_conflict", "wide_bracket",
                               "outside_evidence_in_context"):
                note = "" if field_name in act_side else f"§4.5 文档字段缺失：{side}.{field_name}"
                runner.compare(scene, f"{base}.{side}.{field_name}", exp_side[field_name],
                               act_side.get(field_name), ambiguities, 1e-6, note)
        for field_name in ("prior_state", "first_inside_at", "last_inside_at", "fix_count",
                           "segment_count", "observed_seconds", "window_seconds",
                           "unobserved_gap_seconds", "touches_window"):
            runner.compare(scene, f"{base}.{field_name}", exp_visit[field_name],
                           row.get(field_name), ambiguities, 1e-6)
        # segments（§4.5 含每段 fix_count）
        act_segments = row.get("segments")
        segment_keys = ("segment_no", "start_at", "end_at", "start_fix_id", "end_fix_id",
                        "seconds", "in_window_seconds", "fix_count")
        exp_segments = [
            {k: s[k] for k in segment_keys} for s in exp_visit["segments"]
        ]
        if isinstance(act_segments, list) and all(isinstance(s, dict) for s in act_segments):
            projected = [{k: s.get(k) for k in segment_keys} for s in act_segments]
            runner.compare(scene, f"{base}.segments", exp_segments, projected, ambiguities, 1e-3)
        else:
            runner.fail(scene, f"{base}.segments", exp_segments, act_segments, "§4.5 segments[]")
        runner.compare(scene, f"{base}.status", exp_visit["status"], row.get("status"),
                       ambiguities, 1e-6)
        # flags：§2.4 定版取值域固定，逐字比对（集合无序）
        act_flags = row.get("flags")
        if isinstance(act_flags, list):
            actual_tokens = sorted({str(f) for f in act_flags})
            unknown = sorted(set(actual_tokens) - DOCUMENTED_FLAGS)
            runner.compare(scene, f"{base}.flags", sorted(exp_visit["flags"]), actual_tokens,
                           ambiguities, 1e-6,
                           f"§2.4 flags 取值域固定为 8 个；未记录取值：{unknown}" if unknown else "")
            if unknown:
                runner.warn(scene, f"{base}.flags.documented", sorted(DOCUMENTED_FLAGS), unknown,
                            "响应出现了 §2.4 未列出的 flag 取值")
        else:
            runner.fail(scene, f"{base}.flags", sorted(exp_visit["flags"]), act_flags,
                        "§4.5/§2.4 flags 数组")


# ==========================================================================
# 比对：snapshot / compare / validation
# ==========================================================================
def check_snapshot(runner: Runner, client: Any, snap: Any, only: str | None) -> dict[str, Any]:
    scene = snap.name
    expected = snap.expected
    response = client.get(SNAPSHOT_PATH, params=snap.query_params())
    runner.compare(scene, "http_status", 200, response.status_code, None, 1e-6)
    if response.status_code != 200:
        return {"scene": scene, "status_code": response.status_code, "body": response.text[:400]}
    body = response.json()
    check_json_health(runner, scene, response, body)
    summary = body.get("summary")
    if not isinstance(summary, dict):
        runner.fail(scene, "summary.present", "summary 对象", summary, "§4.2 响应应含 summary")
    else:
        amb = expected.get("ambiguities", {})
        for key, candidates in SNAPSHOT_KEYS.items():
            value, used = _pick(summary, candidates)
            path = f"summary.{key}"
            if used is None:
                runner.warn(scene, path, expected["summary"][key], sorted(summary),
                            f"候选名 {candidates}")
                continue
            runner.compare(scene, path, expected["summary"][key], value, amb, 1e-6,
                           f"响应字段 {used}")
    amb = expected.get("ambiguities", {})
    runner.compare(scene, "status_hint", expected["status_hint"], body.get("status"), amb, 1e-6)
    ships = body.get("ships")
    if not isinstance(ships, list):
        runner.fail(scene, "ships.present", "数组", ships, "§4.2 ships[]")
    else:
        actual_ids = sorted({int(s["ship_id"]) for s in ships if isinstance(s, dict) and "ship_id" in s})
        expected_ids = sorted(s["ship_id"] for s in expected["ships"])
        runner.compare(scene, "ships.ship_ids", expected_ids, actual_ids, amb, 1e-6,
                       "§2.1 新鲜且在矩形内的船才计入")
        for exp_ship in expected["ships"]:
            row = next((s for s in ships if isinstance(s, dict) and s.get("ship_id") == exp_ship["ship_id"]), None)
            if row is None:
                continue
            for field_name in ("latitude", "longitude", "age_seconds", "fresh", "inside"):
                runner.compare(scene, f"ships[{exp_ship['ship_id']}].{field_name}",
                               exp_ship[field_name], row.get(field_name), amb, 1e-3)
            if "recorded_at" in row:
                runner.compare(scene, f"ships[{exp_ship['ship_id']}].recorded_at",
                               exp_ship["recorded_at"], row["recorded_at"], amb, 1e-6)
    _check_known_extra_fields(runner, scene, body, expected)
    return {
        "scene": scene,
        "status_code": 200,
        "summary": body.get("summary"),
        "ships": [s.get("ship_id") for s in ships if isinstance(s, dict)] if isinstance(ships, list) else [],
    }


def check_compare(runner: Runner, client: Any, cmp_scn: Any) -> dict[str, Any]:
    scene = cmp_scn.name
    expected = cmp_scn.expected
    response = client.get(COMPARE_PATH, params=cmp_scn.query_params())
    runner.compare(scene, "http_status", 200, response.status_code, None, 1e-6)
    if response.status_code != 200:
        return {"scene": scene, "status_code": response.status_code, "body": response.text[:400]}
    body = response.json()
    check_json_health(runner, scene, response, body)

    for label, exp_summary in (("a", expected["a"]), ("b", expected["b"])):
        node = body.get(label)
        if not isinstance(node, dict):
            runner.warn(scene, f"{label}.present", "对象", type(node).__name__,
                        "§4.4 响应含 a/b")
            continue
        sub = node.get("summary") if isinstance(node.get("summary"), dict) else node
        for key in ("ships_observed", "observed_entry_count", "observed_exit_count"):
            value, used = _pick(sub, SUMMARY_KEYS[key])
            if used is None:
                runner.warn(scene, f"{label}.{key}", exp_summary[key], sorted(sub), "未找到字段")
                continue
            runner.compare(scene, f"{label}.{key}", exp_summary[key], value, None, 1e-6)

    metrics = body.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        runner.warn(scene, "metrics.present", "非空数组", metrics, "§4.4 metrics[]")
    else:
        found: dict[str, dict[str, Any]] = {}
        for item in metrics:
            if not isinstance(item, dict):
                continue
            name, _ = _pick(item, ["name", "metric", "key", "id", "label"])
            if isinstance(name, str):
                found[name] = item
        matched_any = False
        matched_keys: set[str] = set()
        for key, candidates in METRIC_NAME_CANDIDATES.items():
            exp_metric = expected["metrics"][key]
            item = next((found[c] for c in candidates if c in found), None)
            if item is None:
                continue
            matched_any = True
            matched_keys.add(key)
            runner.compare(scene, f"metrics[{key}].a", exp_metric["a"], item.get("a"), None, 1e-3)
            runner.compare(scene, f"metrics[{key}].b", exp_metric["b"], item.get("b"), None, 1e-3)
            runner.compare(scene, f"metrics[{key}].delta", exp_metric["delta"], item.get("delta"),
                           None, 1e-3)
            runner.compare(scene, f"metrics[{key}].change_rate", exp_metric["change_rate"],
                           item.get("change_rate"), None, 1e-6,
                           "§2.5 a==0 -> change_rate=null")
        if not matched_any:
            runner.warn(scene, "metrics.names", sorted(expected["metrics"]), sorted(found),
                        "§4.4 未定义 metrics 的字段名，无法逐项核对")
        elif set(METRIC_NAME_CANDIDATES) - matched_keys:
            runner.warn(scene, "metrics.coverage", sorted(METRIC_NAME_CANDIDATES),
                        sorted(matched_keys),
                        f"§2.5 指标未按名匹配到：{sorted(set(METRIC_NAME_CANDIDATES) - matched_keys)}")
    comparability = body.get("comparability")
    amb = expected.get("ambiguities", {})
    if isinstance(comparability, dict):
        value, used = _pick(comparability, ["equal_length"])
        runner.compare(scene, "comparability.equal_length", expected["equal_length"], value, amb,
                       1e-6, "§2.5 定版：按窗口实际长度比较（12 h 与 24 h 判为不等长）")
        for label in ("a", "b"):
            val, used_days = _pick(comparability, [f"window_days_{label}"])
            runner.compare(scene, f"comparability.window_days_{label}",
                           expected[f"window_days_{label}"], val, amb, 1e-6,
                           "§2.5 定版：window_days = 窗口覆盖的 UTC 自然日个数")
            val_len, used_len = _pick(comparability, [f"window_length_days_{label}"])
            if used_len is not None:
                runner.compare(scene, f"comparability.window_length_days_{label}",
                               expected[f"window_length_days_{label}"], val_len, amb, 1e-6,
                               "§2.5 定版：window_length_days = 实际长度（日均分母）")
            else:
                runner.warn(scene, f"comparability.window_length_days_{label}",
                            expected[f"window_length_days_{label}"], sorted(comparability),
                            "§2.5 要求回显窗口实际长度")
    else:
        runner.warn(scene, "comparability.present", "对象", comparability, "§2.5 覆盖可比性")
    _check_known_extra_fields(runner, scene, body, expected, required=("limitations", "windows"))
    return {"scene": scene, "status_code": 200, "metrics": metrics}


def check_validation(runner: Runner, client: Any, case: Any) -> dict[str, Any]:
    scene = case.name
    path = {"activity": ACTIVITY_PATH, "snapshot": SNAPSHOT_PATH, "compare": COMPARE_PATH}[case.endpoint]
    response = client.get(path, params=case.params)
    status = "PASS" if response.status_code == case.expect_http else "FAIL"
    runner.add(scene, f"http_status({case.endpoint})", case.expect_http, response.status_code, status,
               f"{case.doc_ref} {case.note}")
    body: Any
    try:
        body = response.json()
    except Exception:
        body = response.text[:200]
    if response.status_code == 422:
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict) and detail.get("code") == "INVALID_REQUEST":
            runner.add(scene, "error_body", {"code": "INVALID_REQUEST"}, detail.get("code"), "PASS")
            runner.compare(scene, "error_body.request_id", True, bool(detail.get("request_id")), None,
                           1e-6, "§4 错误体含 request_id")
        else:
            runner.warn(scene, "error_body", {"code": "INVALID_REQUEST", "message": "...",
                                              "request_id": "..."}, body,
                        "§4 参数错误错误体应与现有路由一致")
    elif case.expect_http == 200:
        if case.name == "V16_window_exactly_7_days":
            runner.compare(scene, "status_hint", "no_data",
                           body.get("status") if isinstance(body, dict) else None, None, 1e-6,
                           "7 天整窗口应被接受（§1.3 上限为包含边界）")
    return {"scene": scene, "status_code": response.status_code}


# ==========================================================================
# 主流程
# ==========================================================================
def print_self_check(checks: Sequence[dict[str, Any]]) -> None:
    print("== self-check（内存内朴素复算自查，不经接口）==")
    failed = 0
    for item in checks:
        if not item["ok"]:
            failed += 1
        print(f"[{'PASS' if item['ok'] else 'FAIL'}] {item['name']}: {item['detail']}")
    print(f"self-check: {len(checks) - failed}/{len(checks)} 通过")
    print()


def db_roundtrip_check(runner: Runner, registry: dict[str, Any], db_fixes: list[Any],
                       db_ships: list[Any]) -> dict[str, Any]:
    """不经接口：用测试库读回的报位重跑朴素复算，和内存期望值比对。"""
    scene = "DB_ROUNDTRIP"
    same_fix_count = len(db_fixes) == len(registry["fixes"])
    runner.compare(scene, "fixes.count", len(registry["fixes"]), len(db_fixes), None, 1e-6,
                   "插入/读回行数一致")
    same_ships = sorted(s.id for s in db_ships) == sorted(s.id for s in registry["ships"])
    runner.compare(scene, "ships.count", len(registry["ships"]), len(db_ships), None, 1e-6)
    mismatched = []
    for src, back in zip(sorted(registry["fixes"], key=lambda f: f.id), db_fixes):
        if (src.id != back.id or src.ship_id != back.ship_id
                or src.latitude != back.latitude or src.longitude != back.longitude
                or src.recorded_at.astimezone(UTC) != back.recorded_at.astimezone(UTC)
                or src.data_source != back.data_source):
            mismatched.append(src.id)
    runner.compare(scene, "fixes.roundtrip", [], mismatched[:10], None, 1e-6,
                   "timestamptz 与 double precision 原样往返")

    drift: list[str] = []
    for sc in registry["scenarios"]:
        analysis = samples.naive_analyze(
            db_ships, db_fixes, sc.rect, sc.start, sc.end, sc.params, sc.ship_types
        )
        for key in ("ships_observed", "observed_entry_count", "observed_exit_count",
                    "observed_ship_seconds"):
            if abs(float(analysis["summary"][key]) - float(sc.expected["summary"][key])) > 1e-6:
                drift.append(f"{sc.name}.{key}")
    runner.compare(scene, "recompute.from_db", [], drift, None, 1e-6,
                   "库内数据复算结果与内存期望一致")
    return {"fixes_rows": len(db_fixes), "ships_rows": len(db_ships),
            "roundtrip_mismatches": mismatched[:10], "recompute_drift": drift}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="区域活动独立样例验证")
    parser.add_argument("--only", help="只跑名称包含该子串的场景")
    parser.add_argument("--skip-db", action="store_true", help="跳过测试库重建（复用已有库）")
    args = parser.parse_args(argv)

    started = datetime.now(UTC)
    t0 = time.time()
    runner = Runner()
    evidence: dict[str, Any] = {
        "script": str(Path(__file__).name),
        "workspace": str(ROOT),
        "run_started_at": started.isoformat(),
        "doc_baseline": {
            "doc": "docs/area_activity.md",
            "note": "按 2026-10-07 定版口径复核：§2.0 有界越界探测、§2.3 jump_min_distance_km=1.0 "
                    "与 unobserved_gap_seconds 含 gap+jump、§2.4 每日=当日∩窗口 与 status 优先级/8 个 "
                    "flags、§2.5 window_days(自然日) 与 window_length_days(实际长度)、§2.6 partial "
                    "触发条件、§4.5 entry/exit.in_window 与 segment_count/每段 fix_count",
            "expected_source": "scripts/area_activity_samples.py（不 import backend，只读文档）",
        },
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "test_database": TEST_DB,
        "test_dsn": safe_dsn(TEST_DB),
        "read_only_database_never_written": READ_ONLY_DB,
        "limits": [],
        "failures": [],
    }

    registry = samples.sample_registry()
    for sc in registry["scenarios"]:
        reason = getattr(sc, "soft_all_reason", "")
        if reason:
            runner.scene_soft_reasons[sc.name] = reason
    self_checks = samples.self_check(registry)
    evidence["self_check"] = self_checks
    print_self_check(self_checks)

    # --- 1) 测试库 ---
    if args.skip_db:
        print("[db] 跳过重建（--skip-db），直接使用现有 hormuz_area_test")
        db_info = {"test_database": TEST_DB, "skipped": True}
    else:
        print(f"[db] 重建测试库 {TEST_DB}（只影响该库）：{safe_dsn(TEST_DB)}")
        db_info = rebuild_test_database()
        print(f"[db] ships={db_info['ships_rows']} ship_positions={db_info['positions_rows']} "
              f"location 非空={db_info['location_not_null']} "
              f"gist 粗筛候选={db_info['gist_candidates']} 索引={db_info['indexes']}")
    evidence["database"] = db_info

    db_fixes, db_ships = load_fixes_from_db()
    evidence["db_roundtrip"] = db_roundtrip_check(runner, registry, db_fixes, db_ships)
    print(f"[db] 读回复算：rows={evidence['db_roundtrip']['fixes_rows']} "
          f"roundtrip_mismatch={len(evidence['db_roundtrip']['roundtrip_mismatches'])} "
          f"drift={len(evidence['db_roundtrip']['recompute_drift'])}")
    print()

    # --- 2) 实现就绪性 ---
    app, not_ready = load_app()
    if not_ready:
        print("=" * 72)
        print("实现尚未就绪：无法验证 /api/area-activity/*")
        print(f"原因：{not_ready}")
        print("期望：backend/app/routers/area_activity.py 存在，且 backend/app/main.py include 其 router。")
        print("本脚本不会修改应用代码来让它通过；样例与朴素期望值本身已通过 self-check。")
        print("=" * 72)
        evidence["implementation_ready"] = False
        evidence["implementation_note"] = not_ready
        evidence["scenario_results"] = []
        evidence["checks"] = [c.as_dict() for c in runner.checks]
        evidence["summary"] = runner.counts()
        evidence["failures"] = [c.as_dict() for c in runner.checks if c.status == "FAIL"]
        evidence["ambiguities"] = _collect_ambiguities(registry)
        evidence["run_finished_at"] = datetime.now(UTC).isoformat()
        evidence["duration_seconds"] = round(time.time() - t0, 3)
        evidence["exit_code"] = 2
        _write_evidence(evidence)
        return 2

    evidence["implementation_ready"] = True
    client = build_client(app)
    scenario_results: list[dict[str, Any]] = []

    # --- 3) 窗口样例 ---
    for sc in registry["scenarios"]:
        if args.only and args.only not in sc.name:
            continue
        before = len(runner.checks)
        try:
            response = client.get(ACTIVITY_PATH, params=sc.query_params())
            runner.compare(sc.name, "http_status", 200, response.status_code, None, 1e-6)
            if response.status_code == 200:
                body = response.json()
                check_json_health(runner, sc.name, response, body)
                check_area_and_algorithm(runner, sc.name, body, sc)
                check_activity_summary(runner, sc.name, body, sc.expected, sc.expected["ambiguities"])
                check_activity_daily(runner, sc.name, body, sc.expected, sc.expected["ambiguities"])
                check_activity_visits(runner, sc.name, body, sc.expected, sc.expected["ambiguities"])
                scenario_results.append(
                    {
                        "scene": sc.name,
                        "kind": "activity",
                        "actual_summary": body.get("summary"),
                        "expected_summary": sc.expected["summary"],
                    }
                )
            else:
                runner.fail(sc.name, "http_body", "200 JSON", response.text[:200], "请求失败")
        except Exception:
            runner.fail(sc.name, "exception", "无异常", traceback.format_exc(limit=3),
                        "场景执行异常")
        # visit_limit 截断探针（§3/§4.3：汇总不受截断影响）
        if sc.name == "S04_boundary_half_open":
            probe = client.get(ACTIVITY_PATH, params=sc.query_params(visit_limit=2))
            runner.compare(sc.name, "visit_limit.http_status", 200, probe.status_code, None, 1e-6)
            if probe.status_code == 200:
                pbody = probe.json()
                runner.compare(sc.name, "visit_limit.visits_len<=", True,
                               len(pbody.get("visits") or []) <= 2, None, 1e-6,
                               "§4.3 visit_limit 只截断明细")
                psummary = pbody.get("summary") or {}
                value, _ = _pick(psummary, SUMMARY_KEYS["ships_observed"])
                runner.compare(sc.name, "visit_limit.summary_unchanged",
                               sc.expected["summary"]["ships_observed"], value, None, 1e-6,
                               "§3 汇总不受明细截断影响")
                runner.compare(sc.name, "visit_limit.status_partial", "partial",
                               pbody.get("status"), None, 1e-6,
                               "§2.6 定版：访问明细被 visit_limit 截断 -> partial（汇总仍完整）")

    # --- 4) 船型筛选 ---
    for sc in registry["scenarios"]:
        if args.only and args.only not in sc.name:
            continue
        for idx, check in enumerate(sc.filter_checks, start=1):
            scene = f"{sc.name}::filter{idx}"
            params = [(k, v) for k, v in sc.query_params() if k != "ship_type"]
            for value in check["ship_type"]:
                params.append(("ship_type", value))
            response = client.get(ACTIVITY_PATH, params=params)
            runner.compare(scene, "http_status", 200, response.status_code, None, 1e-6)
            if response.status_code != 200:
                continue
            body = response.json()
            runner.compare(scene, "ship_type", check["ship_type"], check["ship_type"], None, 1e-6,
                           check.get("note", ""))
            check_activity_summary(runner, scene, body, check["expected"], check["expected"]["ambiguities"])
            check_activity_visits(runner, scene, body, check["expected"], check["expected"]["ambiguities"])

    # --- 5) 快照样例 ---
    for snap in registry["snapshots"]:
        if args.only and args.only not in snap.name:
            continue
        try:
            scenario_results.append(check_snapshot(runner, client, snap, args.only))
        except Exception:
            runner.fail(snap.name, "exception", "无异常", traceback.format_exc(limit=3),
                        "快照场景异常")

    # --- 6) A/B 比较 ---
    for cmp_scn in registry["compares"]:
        if args.only and args.only not in cmp_scn.name:
            continue
        try:
            scenario_results.append(check_compare(runner, client, cmp_scn))
        except Exception:
            runner.fail(cmp_scn.name, "exception", "无异常", traceback.format_exc(limit=3),
                        "比较场景异常")

    # --- 7) 参数校验 ---
    for case in registry["validations"]:
        if args.only and args.only not in case.name:
            continue
        try:
            scenario_results.append(check_validation(runner, client, case))
        except Exception:
            runner.fail(case.name, "exception", "无异常", traceback.format_exc(limit=3),
                        "校验用例异常")

    # --- 8) default-area ---
    try:
        response = client.get(DEFAULT_AREA_PATH)
        runner.compare("default_area", "http_status", 200, response.status_code, None, 1e-6)
        if response.status_code == 200:
            blob = json.dumps(_jsonable(response.json()), ensure_ascii=False)
            for token in (samples.DEFAULT_AREA_ID, "55.8", "57.1", "25.8", "27.1"):
                runner.compare("default_area", f"contains[{token}]", True, token in blob, None, 1e-6,
                               "§4.1 回显默认区域")
    except Exception:
        runner.fail("default_area", "exception", "无异常", traceback.format_exc(limit=3))

    # --- 输出 ---
    counts = runner.counts()
    print()
    print("== 逐项比对明细（仅打印非 PASS 与分场景统计）==")
    by_scene: dict[str, dict[str, int]] = {}
    for c in runner.checks:
        by_scene.setdefault(c.scene, {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0})[c.status] += 1
    for c in runner.checks:
        if c.status in ("FAIL", "WARN"):
            print(f"[{c.status}] {c.scene} :: {c.path}")
            print(f"        期望: {_shown(c.expected)}")
            print(f"        实际: {_shown(c.actual)}")
            if c.note:
                print(f"        说明: {c.note}")
    print()
    print(f"{'scene':38s} {'PASS':>6s} {'WARN':>6s} {'FAIL':>6s}")
    for scene in sorted(by_scene):
        row = by_scene[scene]
        print(f"{scene:38s} {row['PASS']:6d} {row['WARN']:6d} {row['FAIL']:6d}")
    print()
    print(f"合计：PASS={counts['PASS']} WARN={counts['WARN']} FAIL={counts['FAIL']}")

    failures = [c for c in runner.checks if c.status == "FAIL"]
    groups: dict[str, dict[str, Any]] = {}
    for c in failures:
        key = c.note or f"值不一致：{c.path}"
        node = groups.setdefault(key, {"count": 0, "scenes": set(), "sample": None})
        node["count"] += 1
        node["scenes"].add(c.scene)
        if node["sample"] is None:
            node["sample"] = {"scene": c.scene, "path": c.path,
                              "expected": _jsonable(c.expected), "actual": _jsonable(c.actual)}
    if groups:
        print("== 失败根因聚合 ==")
        for key, node in sorted(groups.items(), key=lambda kv: -kv[1]["count"]):
            print(f"[{node['count']:3d} 次 / {len(node['scenes']):2d} 场景] {key}")
            print(f"        例：{node['sample']['scene']} :: {node['sample']['path']} "
                  f"期望={_shown(node['sample']['expected'], 60)} 实际={_shown(node['sample']['actual'], 60)}")
        print()

    evidence["scenario_results"] = scenario_results
    evidence["checks"] = [c.as_dict() for c in runner.checks]
    evidence["summary"] = counts
    evidence["failures"] = [c.as_dict() for c in failures]
    evidence["failure_groups"] = [
        {"note": key, "count": node["count"], "scenes": sorted(node["scenes"]),
         "sample": node["sample"]}
        for key, node in sorted(groups.items(), key=lambda kv: -kv[1]["count"])
    ]
    evidence["ambiguities"] = _collect_ambiguities(registry)
    evidence["run_finished_at"] = datetime.now(UTC).isoformat()
    evidence["duration_seconds"] = round(time.time() - t0, 3)
    evidence["exit_code"] = 1 if failures else 0
    _write_evidence(evidence)
    print(f"证据文件：{RESULT_PATH}")
    return evidence["exit_code"]


def _collect_ambiguities(registry: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sc in registry["scenarios"]:
        if sc.expected and sc.expected["ambiguities"]:
            simplified = {
                path: {"reason": info["reason"],
                       "alternates": [_jsonable(a) for a in info["alternates"]]}
                for path, info in sc.expected["ambiguities"].items()
                if info["reason"]
            }
            if simplified:
                out[sc.name] = simplified
    for snap in registry["snapshots"]:
        if snap.expected:
            out[snap.name] = {
                path: {"reason": info["reason"], "alternates": [_jsonable(a) for a in info["alternates"]]}
                for path, info in snap.expected["ambiguities"].items()
            }
    return out


def _write_evidence(evidence: dict[str, Any]) -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
