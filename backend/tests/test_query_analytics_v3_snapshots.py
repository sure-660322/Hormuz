"""SQL-03/04 catalog v3 受控分析快照离线测试（issue #48）。

不连接真实数据库：
- 策略层：快照表 required_filters 各分支（缺边界/单边界/反序/超范围/
  BETWEEN 形式/area_id 缺失/IN 形式/列比较非参数边界/老视图不受影响）；
- 执行器层：用假连接直接驱动 _verify_catalog，核验 kind=table 的
  列签名路径、kind=view 的哈希路径与 v_snapshot_manifest 清单行
  缺失时 fail closed。
"""
from __future__ import annotations

import pytest

from backend.app.services.agent.query_analytics_executor import (
    CatalogMismatchError,
    ExecutorConfig,
    QueryAnalyticsExecutor,
)
from backend.app.services.agent.query_analytics_policy import (
    QueryRefusedError,
    load_catalog,
    validate_query,
)

DAY1 = "2026-02-25T00:00:00+00:00"
DAY2 = "2026-02-26T00:00:00+00:00"
DAY8 = "2026-03-04T00:00:00+00:00"
DATE1 = "2026-02-25"
DATE8 = "2026-03-04"


def param(name, type_, value):
    return {"name": name, "type": type_, "value": value}


# ------------------------------------------------------------ 策略层：必要过滤

def _evidence(sql_where: str, params: list):
    sql = f"SELECT passage_key FROM agent_data.v_passage_evidence WHERE {sql_where}"
    return validate_query(sql, params, purpose="离线测试")


def test_evidence_table_without_time_bounds_is_refused():
    with pytest.raises(QueryRefusedError, match="双边界"):
        validate_query(
            "SELECT passage_key FROM agent_data.v_passage_evidence WHERE direction = :p",
            [param("p", "text", "west_to_east")],
        )


def test_evidence_table_single_bound_is_refused():
    with pytest.raises(QueryRefusedError, match="双边界"):
        _evidence("observed_completion_at >= :low",
                  [param("low", "timestamptz", DAY1)])
    with pytest.raises(QueryRefusedError, match="双边界"):
        _evidence("observed_completion_at <= :high",
                  [param("high", "timestamptz", DAY2)])


def test_evidence_table_span_over_24h_is_refused():
    with pytest.raises(QueryRefusedError, match="超过"):
        _evidence(
            "observed_completion_at >= :low AND observed_completion_at < :high",
            [param("low", "timestamptz", DAY1), param("high", "timestamptz", DAY8)],
        )


def test_evidence_table_exact_24h_window_is_allowed():
    result = _evidence(
        "observed_completion_at >= :low AND observed_completion_at < :high",
        [param("low", "timestamptz", DAY1), param("high", "timestamptz", DAY2)],
    )
    assert result.catalog_version == "3.0"
    assert result.referenced_views == ("agent_data.v_passage_evidence",)


def test_evidence_table_between_form_is_allowed():
    result = _evidence(
        "observed_completion_at BETWEEN :low AND :high",
        [param("low", "timestamptz", DAY1), param("high", "timestamptz", DAY2)],
    )
    assert result.normalized_sql.startswith("SELECT")


def test_evidence_table_reversed_bounds_are_refused():
    with pytest.raises(QueryRefusedError, match="下界必须早于上界"):
        _evidence(
            "observed_completion_at >= :low AND observed_completion_at < :high",
            [param("low", "timestamptz", DAY2), param("high", "timestamptz", DAY1)],
        )


def test_evidence_table_column_comparison_bound_is_refused():
    """边界必须是绑定参数：列与列比较不构成合法时间边界。"""
    with pytest.raises(QueryRefusedError, match="绑定参数"):
        _evidence(
            "observed_completion_at >= start_observed_at "
            "AND observed_completion_at < :high",
            [param("high", "timestamptz", DAY2)],
        )


def test_daily_table_span_over_7_days_is_refused():
    with pytest.raises(QueryRefusedError, match="超过"):
        validate_query(
            "SELECT day, confirmed_passage_count FROM agent_data.v_passage_daily "
            "WHERE day >= :low AND day < :high",
            [param("low", "date", "2026-02-24"), param("high", "date", DATE8)],
        )


def test_daily_table_7_day_span_is_allowed():
    result = validate_query(
        "SELECT day, confirmed_passage_count FROM agent_data.v_passage_daily "
        "WHERE day >= :low AND day <= :high",
        [param("low", "date", DATE1), param("high", "date", "2026-03-03")],
    )
    assert result.referenced_views == ("agent_data.v_passage_daily",)


def test_area_visit_without_area_id_is_refused():
    with pytest.raises(QueryRefusedError, match="area_id"):
        validate_query(
            "SELECT visit_key FROM agent_data.v_area_visit "
            "WHERE first_inside_at >= :low AND first_inside_at < :high",
            [param("low", "timestamptz", DAY1), param("high", "timestamptz", DAY2)],
        )


def test_area_visit_with_area_id_and_bounds_is_allowed():
    result = validate_query(
        "SELECT visit_key FROM agent_data.v_area_visit "
        "WHERE area_id = :area AND first_inside_at >= :low AND first_inside_at < :high",
        [param("area", "text", "hormuz_core_v1"),
         param("low", "timestamptz", DAY1), param("high", "timestamptz", DAY2)],
    )
    assert result.referenced_views == ("agent_data.v_area_visit",)


def test_area_visit_area_id_in_form_is_allowed():
    result = validate_query(
        "SELECT visit_key FROM agent_data.v_area_visit "
        "WHERE area_id IN (:a1, :a2) AND first_inside_at >= :low "
        "AND first_inside_at < :high",
        [param("a1", "text", "hormuz_core_v1"), param("a2", "text", "other_area"),
         param("low", "timestamptz", DAY1), param("high", "timestamptz", DAY2)],
    )
    assert result.catalog_version == "3.0"


def test_area_daily_requires_area_id_and_bounded_day():
    with pytest.raises(QueryRefusedError, match="area_id"):
        validate_query(
            "SELECT day, ships_observed FROM agent_data.v_area_daily "
            "WHERE day >= :low AND day < :high",
            [param("low", "date", DATE1), param("high", "date", DATE8)],
        )
    result = validate_query(
        "SELECT day, ships_observed FROM agent_data.v_area_daily "
        "WHERE area_id = :area AND day >= :low AND day < :high",
        [param("area", "text", "hormuz_core_v1"),
         param("low", "date", DATE1), param("high", "date", DATE8)],
    )
    assert result.referenced_views == ("agent_data.v_area_daily",)


def test_coverage_table_requires_bounded_day():
    with pytest.raises(QueryRefusedError, match="双边界"):
        validate_query(
            "SELECT day, position_count FROM agent_data.v_data_coverage",
            [],
        )
    result = validate_query(
        "SELECT day, position_count FROM agent_data.v_data_coverage "
        "WHERE day >= :low AND day < :high",
        [param("low", "date", DATE1), param("high", "date", DATE8)],
    )
    assert result.referenced_views == ("agent_data.v_data_coverage",)


def test_legacy_views_have_no_required_filters():
    """老视图（kind=view）不带 required_filters，无时间过滤的查询不受影响。"""
    result = validate_query(
        "SELECT ship_id FROM agent_data.v_ships WHERE name LIKE :p",
        [param("p", "text", "%NOVA%")],
    )
    assert result.catalog_version == "3.0"


# ------------------------------------------------------------ 执行器层：假连接

_SENTINEL = object()


class _Result:
    def __init__(self, *, scalar=_SENTINEL, rows=(), mapping=None):
        self._scalar = scalar
        self._rows = list(rows)
        self._mapping = mapping

    def scalar_one(self):
        assert self._scalar is not _SENTINEL
        return self._scalar

    def all(self):
        return list(self._rows)

    def one(self):
        assert len(self._rows) == 1
        return self._rows[0]

    def one_or_none(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        outer = self

        class _Mappings:
            def one_or_none(self_inner):
                return outer._mapping

        return _Mappings()


def _offline_executor() -> QueryAnalyticsExecutor:
    config = ExecutorConfig(
        enabled=True, db_user="agent_reader_login", db_password="placeholder",
        db_host="127.0.0.1", db_port=5432, db_name="fixture",
    )
    return QueryAnalyticsExecutor(config, engine=object())


def _fake_connection(catalog: dict, *, manifest_counts: dict | None = None,
                     column_overrides: dict | None = None):
    """按 catalog 生成与 _verify_catalog 查询一一对应的假连接。

    执行器对 pg_get_viewdef 返回的**定义文本**做 SHA-256 后再比对 catalog
    哈希，因此本函数为每个 kind=view 条目生成固定假定义文本，并把 catalog
    中的 definition_sha256 同步改写为同一文本的哈希（调用方传入的 catalog
    会被就地修改，每个测试都应重新 load_catalog）。
    """
    import hashlib

    manifest_counts = manifest_counts or {}
    column_overrides = column_overrides or {}
    viewdefs: dict[str, str] = {}
    for view in catalog["views"]:
        if view.get("kind", "view") == "view":
            text = f"/* fake viewdef for {view['name']} */"
            viewdefs[view["name"]] = text
            view["definition_sha256"] = hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest()
    views = {v["name"]: v for v in catalog["views"]}
    meta_tables = {t["name"]: t for t in catalog.get("meta_tables", [])}
    relation_names = tuple(sorted([*views.keys(), *meta_tables.keys()]))
    login_role = {
        "rolname": "agent_reader_login", "rolsuper": False, "rolcreatedb": False,
        "rolcreaterole": False, "rolcanlogin": True, "rolinherit": True,
        "rolreplication": False, "rolbypassrls": False, "rolconnlimit": 4,
    }

    class _Conn:
        def exec_driver_sql(self, sql, params=None):
            params = params or {}
            flat = " ".join(sql.split())
            if "server_version_num" in flat:
                return _Result(scalar=catalog["postgres_major"])
            if "FROM pg_roles WHERE rolname = current_user" in flat:
                return _Result(mapping=login_role)
            if "pg_auth_members" in flat:
                return _Result(rows=(("agent_reader_login", "agent_reader"),))
            if "'agent_reader', 'agent_view_owner'" in flat:
                return _Result(rows=(
                    ("agent_reader",) + (False,) * 7,
                    ("agent_view_owner",) + (False,) * 7,
                ))
            if "FROM pg_namespace" in flat:
                return _Result(rows=(("agent_data",),))
            if "has_schema_privilege" in flat:
                return _Result(rows=((True, False, False, False),))
            if "n.nspname || '.' || c.relname" in flat:
                return _Result(rows=((name,) for name in relation_names))
            if "FROM pg_proc" in flat:
                return _Result(scalar=0)
            if "pg_get_viewdef" in flat:
                return _Result(scalar=viewdefs[params["view_name"]])
            if "information_schema.columns" in flat:
                name = params["view_name"]
                columns = column_overrides.get(name, views[name]["columns"])
                return _Result(rows=tuple(
                    (c["name"], c["postgres_type"], bool(c["nullable"]))
                    for c in columns
                ))
            if "v_snapshot_manifest" in flat:
                snapshot = params["snapshot"]
                count = manifest_counts.get(snapshot, 1)
                return _Result(scalar=count)
            if "pg_get_userbyid" in flat:
                if "view_name" in params:
                    return _Result(rows=((views[params["view_name"]]["owner"], True),))
                table = meta_tables[params["name"]]
                return _Result(rows=((table["owner"], True),))
            if "n.nspname = 'public'" in flat:
                return _Result(rows=tuple(
                    (name, False)
                    for name in ("events", "news", "ship_positions", "ships")
                ))
            raise AssertionError(f"未预期的查询：{flat}")

    return _Conn()


def test_verify_catalog_passes_for_consistent_v3_database():
    catalog = load_catalog()
    executor = _offline_executor()
    checks = executor._verify_catalog(_fake_connection(catalog), catalog)
    assert checks
    assert "manifest_row:agent_data.v_snapshot_manifest" in checks
    assert "view_columns:agent_data.v_passage_evidence" in checks


def test_missing_manifest_row_fails_closed():
    catalog = load_catalog()
    executor = _offline_executor()
    connection = _fake_connection(catalog, manifest_counts={"analysis_batch_v1": 0})
    with pytest.raises(CatalogMismatchError) as caught:
        executor._verify_catalog(connection, catalog)
    assert "manifest_row:agent_data.v_snapshot_manifest" in caught.value.mismatches


def test_snapshot_table_column_drift_fails_closed():
    catalog = load_catalog()
    executor = _offline_executor()
    drifted_columns = [
        {"name": "passage_key", "postgres_type": "text", "nullable": True},
        *[c for c in catalog["views"][3]["columns"] if c["name"] != "passage_key"],
    ]
    connection = _fake_connection(
        catalog,
        column_overrides={"agent_data.v_passage_evidence": drifted_columns},
    )
    with pytest.raises(CatalogMismatchError) as caught:
        executor._verify_catalog(connection, catalog)
    assert "view_columns:agent_data.v_passage_evidence" in caught.value.mismatches


def test_legacy_view_hash_drift_fails_closed():
    catalog = load_catalog()
    executor = _offline_executor()
    connection = _fake_connection(catalog)
    # 假连接已把 catalog 哈希同步为假定义文本的哈希；这里再改回制造漂移。
    catalog["views"][0]["definition_sha256"] = "0" * 64
    with pytest.raises(CatalogMismatchError) as caught:
        executor._verify_catalog(connection, catalog)
    assert "view_hash:agent_data.v_ships" in caught.value.mismatches
