"""SQL-03 offline allow/refuse tests. No database or model connection."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.services.agent.query_analytics_policy import (
    MAX_AST_DEPTH,
    MAX_AST_NODES,
    MAX_GROUP_ITEMS,
    MAX_ORDER_ITEMS,
    MAX_PARAMS,
    MAX_PROJECTIONS,
    QueryInputError,
    QueryPolicyError,
    QueryRefusedError,
    QuerySyntaxError,
    SQLGLOT_VERSION,
    validate_query,
)


def param(name, type_, value):
    return {"name": name, "type": type_, "value": value}


CATALOG_COLUMNS = {
    "v_ships": [
        "ship_id", "name", "mmsi", "imo", "callsign", "ship_type", "flag",
        "data_source", "is_simulated",
    ],
    "v_events": [
        "event_id", "event_type", "representative_latitude",
        "representative_longitude", "event_datetime", "earliest_report_date",
        "latest_report_date",
    ],
    "v_news": [
        "news_id", "event_id", "title", "reported_date", "source_name", "source_url",
    ],
}


ALLOW_CASES = [
    (f"SELECT {column} FROM agent_data.{view}", [])
    for view, columns in CATALOG_COLUMNS.items()
    for column in columns
] + [
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = :p", [param("p", "text", "shipping")]),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type <> :p", [param("p", "text", "shipping")]),
    ("SELECT event_id FROM agent_data.v_events WHERE representative_latitude > :p", [param("p", "numeric", 25.0)]),
    ("SELECT event_id FROM agent_data.v_events WHERE representative_longitude <= :p", [param("p", "numeric", 57.0)]),
    ("SELECT event_id FROM agent_data.v_events WHERE event_datetime >= :p", [param("p", "timestamptz", "2026-01-01T00:00:00Z")]),
    ("SELECT event_id FROM agent_data.v_events WHERE earliest_report_date = :p", [param("p", "date", "2026-01-01")]),
    ("SELECT ship_id FROM agent_data.v_ships WHERE ship_id = :p", [param("p", "int", 1)]),
    ("SELECT ship_id FROM agent_data.v_ships WHERE is_simulated = :p", [param("p", "bool", True)]),
    ("SELECT ship_id FROM agent_data.v_ships WHERE name LIKE :p", [param("p", "text", "%SIM%")]),
    ("SELECT news_id FROM agent_data.v_news WHERE event_id IN (:p1, :p2)", [param("p1", "text", "evt_1"), param("p2", "text", "evt_2")]),
    ("SELECT news_id FROM agent_data.v_news WHERE reported_date BETWEEN :p1 AND :p2", [param("p1", "date", "2026-01-01"), param("p2", "date", "2026-01-31")]),
    ("SELECT news_id FROM agent_data.v_news WHERE event_id IS NULL", []),
    ("SELECT news_id FROM agent_data.v_news WHERE event_id IS NOT NULL", []),
    ("SELECT event_id FROM agent_data.v_events ORDER BY event_id LIMIT 10", []),
    ("SELECT news_id FROM agent_data.v_news ORDER BY reported_date DESC LIMIT 20 OFFSET 0", []),
    ("SELECT event_type, COUNT(*) AS event_count FROM agent_data.v_events GROUP BY event_type ORDER BY event_type", []),
    ("SELECT event_type, COUNT(*) AS event_count FROM agent_data.v_events GROUP BY event_type ORDER BY event_count DESC", []),
    ("SELECT COUNT(event_id) AS event_count FROM agent_data.v_events", []),
    ("SELECT MIN(earliest_report_date) AS min_date FROM agent_data.v_events", []),
    ("SELECT MAX(latest_report_date) AS max_date FROM agent_data.v_events", []),
    ("SELECT AVG(representative_latitude) AS avg_latitude FROM agent_data.v_events", []),
    ("SELECT SUM(representative_longitude) AS longitude_sum FROM agent_data.v_events", []),
    ("SELECT UPPER(event_type) AS upper_type FROM agent_data.v_events", []),
    ("SELECT LOWER(event_type) AS lower_type FROM agent_data.v_events", []),
    ("SELECT LENGTH(event_type) AS type_length FROM agent_data.v_events", []),
    ("SELECT COALESCE(event_type, :fallback) AS safe_type FROM agent_data.v_events", [param("fallback", "text", "unknown")]),
    ("SELECT DATE_TRUNC(:unit, event_datetime) AS event_bucket FROM agent_data.v_events", [param("unit", "text", "day")]),
    ("SELECT EXTRACT(YEAR FROM event_datetime) AS event_year FROM agent_data.v_events", []),
    ("SELECT CAST(:p AS text) AS typed_value FROM agent_data.v_events LIMIT 1", [param("p", "text", "x")]),
    ("SELECT representative_latitude + :delta AS shifted_latitude FROM agent_data.v_events", [param("delta", "numeric", 1.5)]),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = :p1 AND event_datetime >= :p2", [param("p1", "text", "shipping"), param("p2", "timestamptz", "2026-01-01T00:00:00Z")]),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = :p1 OR event_type = :p2", [param("p1", "text", "shipping"), param("p2", "text", "security")]),
    ("SELECT event_id FROM agent_data.v_events WHERE NOT event_type = :p", [param("p", "text", "shipping")]),
    ("SELECT v_news.news_id, v_events.event_type FROM agent_data.v_news INNER JOIN agent_data.v_events ON v_news.event_id = v_events.event_id", []),
    ("SELECT n.news_id, e.event_type FROM agent_data.v_news AS n LEFT JOIN agent_data.v_events AS e ON n.event_id = e.event_id WHERE e.event_type = :p", [param("p", "text", "shipping")]),
    ("SELECT e.event_id, n.news_id FROM agent_data.v_events AS e LEFT JOIN agent_data.v_news AS n ON e.event_id = n.event_id ORDER BY e.event_id", []),
]


@pytest.mark.parametrize("sql,params", ALLOW_CASES)
def test_allowed_queries(sql, params):
    result = validate_query(sql, params, purpose="离线测试")
    assert result.catalog_version == "1.0"
    assert result.normalized_sql.startswith("SELECT")
    assert 1 <= result.ast_node_count <= MAX_AST_NODES
    assert result.referenced_views


REJECT_CASES = [
    ("SELECT 1", []),
    ("SELECT event_type FROM v_events", []),
    ("SELECT event_type FROM public.events", []),
    ("SELECT event_type FROM other.v_events", []),
    ("SELECT event_type FROM agent_data.unknown", []),
    ("SELECT unknown FROM agent_data.v_events", []),
    ("SELECT * FROM agent_data.v_events", []),
    ("SELECT v_events.* FROM agent_data.v_events", []),
    ("SELECT event_type FROM agent_data.v_events -- comment", []),
    ("SELECT event_type /* comment */ FROM agent_data.v_events", []),
    ("SELECT event_type FROM agent_data.v_events; SELECT event_id FROM agent_data.v_events", []),
    ("INSERT INTO agent_data.v_events(event_type) VALUES (:p)", [param("p", "text", "x")]),
    ("UPDATE agent_data.v_events SET event_type = :p", [param("p", "text", "x")]),
    ("DELETE FROM agent_data.v_events", []),
    ("DROP VIEW agent_data.v_events", []),
    ("SELECT event_type INTO temp_x FROM agent_data.v_events", []),
    ("SELECT event_type FROM agent_data.v_events FOR UPDATE", []),
    ("WITH q AS (SELECT event_type FROM agent_data.v_events) SELECT event_type FROM q", []),
    ("SELECT event_type FROM agent_data.v_events UNION SELECT event_type FROM agent_data.v_events", []),
    ("SELECT event_type FROM agent_data.v_events WHERE event_id IN (SELECT event_id FROM agent_data.v_news)", []),
    ("SELECT event_type, ROW_NUMBER() OVER () AS row_number FROM agent_data.v_events", []),
    ("SELECT DISTINCT event_type FROM agent_data.v_events", []),
    ("SELECT CASE WHEN event_type = :p THEN event_type END FROM agent_data.v_events", [param("p", "text", "x")]),
    ("SELECT event_type || :p FROM agent_data.v_events", [param("p", "text", "x")]),
    ("SELECT event_type ILIKE :p FROM agent_data.v_events", [param("p", "text", "%x%")]),
    ("SELECT NOW() FROM agent_data.v_events", []),
    ("SELECT pg_sleep(:p) FROM agent_data.v_events", [param("p", "numeric", 1)]),
    ("SELECT agent_data.evil(event_type) FROM agent_data.v_events", []),
    ("SELECT CAST(event_type AS jsonb) FROM agent_data.v_events", []),
    ("SELECT TRY_CAST(event_type AS text) FROM agent_data.v_events", []),
    ("SELECT SUM(event_type) FROM agent_data.v_events", []),
    ("SELECT UPPER(event_datetime) FROM agent_data.v_events", []),
    ("SELECT DATE_TRUNC(:unit, event_type) FROM agent_data.v_events", [param("unit", "text", "day")]),
    ("SELECT DATE_TRUNC(event_type, event_datetime) FROM agent_data.v_events", []),
    ("SELECT EXTRACT(YEAR FROM event_type) FROM agent_data.v_events", []),
    ("SELECT event_type + :p FROM agent_data.v_events", [param("p", "numeric", 1)]),
    ("SELECT event_type LIKE :p FROM agent_data.v_events", [param("p", "int", 1)]),
    ("SELECT event_id FROM agent_data.v_events WHERE NOT event_type", []),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type IS TRUE", []),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = 'shipping'", []),
    ("SELECT event_id FROM agent_data.v_events WHERE event_datetime >= TIMESTAMP '2026-01-01'", []),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = E'shipping'", []),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = $tag$shipping$tag$", []),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = U&'shipping'", []),
    ("SELECT event_id AS status FROM agent_data.v_events", []),
    ("SELECT event_id AS BadAlias FROM agent_data.v_events", []),
    ("SELECT event_id AS same_name, event_type AS same_name FROM agent_data.v_events", []),
    ("SELECT event_id FROM agent_data.v_events LIMIT -1", []),
    ("SELECT event_id FROM agent_data.v_events LIMIT :limit", [param("limit", "int", 10)]),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = :missing", []),
    ("SELECT event_id FROM agent_data.v_events", [param("extra", "text", "x")]),
    ("SELECT event_id FROM agent_data.v_events WHERE event_type = :p", [param("p", "int", 1)]),
    ("SELECT event_id, COUNT(*) FROM agent_data.v_events", []),
    ("SELECT event_id FROM agent_data.v_events JOIN agent_data.v_news ON v_events.event_id = v_news.event_id JOIN agent_data.v_ships ON v_ships.ship_id = v_events.event_id", []),
    ("SELECT event_id FROM agent_data.v_events RIGHT JOIN agent_data.v_news ON v_events.event_id = v_news.event_id", []),
    ("SELECT event_id FROM agent_data.v_events FULL JOIN agent_data.v_news ON v_events.event_id = v_news.event_id", []),
    ("SELECT event_id FROM agent_data.v_events CROSS JOIN agent_data.v_news", []),
    ("SELECT event_id FROM agent_data.v_events JOIN agent_data.v_news USING (event_id)", []),
    ("SELECT v_events.event_id FROM agent_data.v_events JOIN agent_data.v_news ON v_events.event_id = v_news.news_id", []),
    ("SELECT event_id FROM agent_data.v_events JOIN agent_data.v_news ON v_events.event_id = v_news.event_id", []),
    ("SELECT event_id FROM agent_data.v_events JOIN agent_data.v_ships ON v_events.event_id = v_ships.name", []),
    ("SELECT n.news_id FROM agent_data.v_news n LEFT JOIN agent_data.v_events e ON n.event_id = e.event_id AND e.event_type = :p", [param("p", "text", "shipping")]),
]


@pytest.mark.parametrize("sql,params", REJECT_CASES)
def test_refused_queries(sql, params):
    with pytest.raises(QueryPolicyError) as captured:
        validate_query(sql, params)
    assert captured.value.retryable is False


def test_ordinary_syntax_error_is_the_only_retryable_failure():
    with pytest.raises(QuerySyntaxError) as captured:
        validate_query("SELECT ( FROM agent_data.v_events")
    assert captured.value.retryable is True


def test_duplicate_parameter_is_rejected():
    with pytest.raises(QueryInputError):
        validate_query(
            "SELECT event_id FROM agent_data.v_events WHERE event_type = :p",
            [param("p", "text", "x"), param("p", "text", "x")],
        )


def test_input_resource_limits_are_enforced_before_parse():
    with pytest.raises(QueryInputError):
        validate_query(" " * (16 * 1024 + 1))
    with pytest.raises(QueryInputError):
        validate_query("SELECT event_id FROM agent_data.v_events", purpose="x" * 501)
    with pytest.raises(QueryInputError):
        validate_query("SELECT event_id FROM agent_data.v_events", [param("p", "text", "x" * 9000)])

    too_many = [param(f"p{index}", "text", "x") for index in range(MAX_PARAMS + 1)]
    with pytest.raises(QueryInputError):
        validate_query("SELECT event_id FROM agent_data.v_events", too_many)

    large_values = [param(f"p{index}", "text", "x" * 8000) for index in range(9)]
    placeholders = ", ".join(f":p{index}" for index in range(9))
    with pytest.raises(QueryInputError):
        validate_query(
            f"SELECT event_id FROM agent_data.v_events WHERE event_type IN ({placeholders})",
            large_values,
        )


def test_structural_complexity_limits_are_enforced():
    projections = ", ".join("event_id" for _ in range(MAX_PROJECTIONS + 1))
    with pytest.raises(QueryRefusedError):
        validate_query(f"SELECT {projections} FROM agent_data.v_events")

    order_items = ", ".join("event_id" for _ in range(MAX_ORDER_ITEMS + 1))
    with pytest.raises(QueryRefusedError):
        validate_query(f"SELECT event_id FROM agent_data.v_events ORDER BY {order_items}")

    group_items = ", ".join("event_id" for _ in range(MAX_GROUP_ITEMS + 1))
    with pytest.raises(QueryRefusedError):
        validate_query(f"SELECT event_id FROM agent_data.v_events GROUP BY {group_items}")

    nested = "event_type = :p"
    for _ in range(MAX_AST_DEPTH + 2):
        nested = f"({nested})"
    with pytest.raises(QueryRefusedError):
        validate_query(
            f"SELECT event_id FROM agent_data.v_events WHERE {nested}",
            [param("p", "text", "shipping")],
        )

    predicates = " OR ".join("event_type = :p" for _ in range(MAX_AST_NODES))
    with pytest.raises(QueryRefusedError):
        validate_query(
            f"SELECT event_id FROM agent_data.v_events WHERE {predicates}",
            [param("p", "text", "shipping")],
        )


def test_identifier_and_parameter_value_types_are_enforced():
    with pytest.raises(QueryPolicyError):
        validate_query(
            f"SELECT event_id AS {'a' * 64} FROM agent_data.v_events"
        )
    with pytest.raises(QueryInputError):
        validate_query(
            "SELECT event_id FROM agent_data.v_events WHERE earliest_report_date = :p",
            [param("p", "date", "not-a-date")],
        )
    with pytest.raises(QueryInputError):
        validate_query(
            "SELECT event_id FROM agent_data.v_events WHERE event_datetime = :p",
            [param("p", "timestamptz", "2026-01-01T00:00:00")],
        )


def test_comments_inside_bound_values_are_data_not_sql_tokens():
    result = validate_query(
        "SELECT event_id FROM agent_data.v_events WHERE event_type = :p",
        [param("p", "text", "' OR 1=1 --")],
    )
    assert result.params[0].value == "' OR 1=1 --"


def test_function_signatures_and_aliased_relations_are_semantically_checked():
    with pytest.raises(QueryRefusedError):
        validate_query("SELECT COUNT() FROM agent_data.v_events")
    with pytest.raises(QueryRefusedError):
        validate_query("SELECT COALESCE(event_type) FROM agent_data.v_events")
    with pytest.raises(QueryRefusedError):
        validate_query("SELECT EXTRACT(EPOCH FROM event_datetime) FROM agent_data.v_events")
    with pytest.raises(QueryRefusedError):
        validate_query(
            "SELECT v_events.event_id FROM agent_data.v_events AS e"
        )


def test_pinned_parser_and_same_ast_normalization():
    result = validate_query(
        "select event_id from agent_data.v_events where event_type=:p",
        [param("p", "text", "shipping")],
    )
    assert SQLGLOT_VERSION == "30.18.0"
    assert result.normalized_sql == (
        "SELECT event_id FROM agent_data.v_events WHERE event_type = %(p)s"
    )
    reparsed = validate_query(result.normalized_sql, [param("p", "text", "shipping")])
    assert reparsed.normalized_sql == result.normalized_sql


def test_at_least_fifty_allow_and_fifty_refuse_cases():
    assert len(ALLOW_CASES) >= 50
    assert len(REJECT_CASES) >= 50
