"""Service layer for P5 /api/data-health: source coverage + derived freshness.

Answers "how fresh is each derived layer, and what parameters was it built
with" plus source coverage stats — the first tool for gap triage when real
data lands (plan section 6).
"""
import json

from sqlalchemy.orm import Session

from backend.app.repositories import data_health as health_repo


def get_data_health(db: Session) -> dict:
    sources = health_repo.fetch_source_counts(db)
    global_counts = health_repo.fetch_global_counts(db)
    manifests = health_repo.fetch_derived_manifests(db)

    latest_source_end = max(
        (row["coverage_end"] for row in sources if row["coverage_end"]), default=None
    )

    derived = []
    for row in manifests:
        params = row["params"] if isinstance(row["params"], dict) else json.loads(row["params"])
        derived.append({
            "table": row["table_name"],
            "rows": row["row_count"],
            "built_at": row["built_at"],
            # 无源报位时间基准时 stale 不可判定，必须为 None；
            # 缺数据不能回答成「未过期」（stale=false）
            "stale": None if latest_source_end is None else row["built_at"] < latest_source_end,
            "params": params,
        })
    built_tables = {row["table"] for row in derived}
    for table in health_repo.DERIVED_TABLES:
        if table not in built_tables:
            derived.append({"table": table, "rows": None, "built_at": None,
                            "stale": None, "params": None,
                            "status": "not_built"})

    return {
        "status": "ok",
        "batch": "sim_ais_demo/output_news_aligned",
        "source": {
            "by_data_source": sources,
            "totals": global_counts,
        },
        "derived": derived,
        "note": "data_source 标识船位来源；stale 表示派生层早于最新源报位，需重建",
    }
