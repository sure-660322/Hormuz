"""船型候选目录：供前端筛选与智能体描述可用船型（只读）。

取值来自 `ships.ship_type` 的真实分布，不在代码里硬编码：新增船型会直接出现在
目录中。为空/NULL 归到保留值 `__missing__`；`未知` 是数据库里的真实取值，归到
保留值 `__unknown__`。两者与 service 的筛选映射一致（见 docs/area_activity.md §3）。
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.services.area_activity import params

# `ships.ship_type` 里「未知」是真实取值，而筛选保留值是 ASCII 的 `__unknown__`；
# service._resolve_filters 用 unknown_label="未知" 过滤。两处必须一致，这里显式写出来，
# 若将来 service 改了标签，本模块的目录映射也要同步改。
UNKNOWN_RAW_LABEL = "未知"

CATALOG_LIMITATIONS = [
    "船型来自 ships 表的当前取值分布，是当前快照属性，不代表历史船型已逐条核实",
    "不按船名推断船型；未识别取值进入「未知」，空值/缺失进入「缺失」",
]

_QUERY = text(
    """
    SELECT
        coalesce(btrim(ship_type), :missing_label) AS raw_value,
        count(*) AS ship_count
    FROM ships
    GROUP BY 1
    ORDER BY ship_count DESC, raw_value ASC
    """
)


def _value_for(raw_value: str) -> str:
    """保留值映射：空值/缺失与「未知」各自归到 service 能精确匹配的筛选值。"""
    if raw_value in ("", params.SHIP_TYPE_MISSING):
        return params.SHIP_TYPE_MISSING
    if raw_value == UNKNOWN_RAW_LABEL:
        return params.SHIP_TYPE_UNKNOWN
    return raw_value


def _label_for(value: str) -> str:
    if value == params.SHIP_TYPE_MISSING:
        return "缺失（空值或 NULL）"
    if value == params.SHIP_TYPE_UNKNOWN:
        return UNKNOWN_RAW_LABEL
    return value


def ship_type_catalog(db: Session) -> dict:
    """按数量降序返回船型目录；空表时返回有效零结果而不是错误。

    同一筛选值可能来自多个原始取值（`__missing__` 覆盖 NULL 与空字符串），
    这里按筛选值聚合，保证目录里的 count 之和等于 `total_ships`。
    """
    rows = db.execute(_QUERY, {"missing_label": params.SHIP_TYPE_MISSING}).fetchall()
    merged: dict[str, dict] = {}
    for raw_value, ship_count in rows:
        raw = "" if raw_value is None else str(raw_value)
        value = _value_for(raw)
        entry = merged.setdefault(
            value,
            {
                "value": value,
                "label": _label_for(value),
                "raw_values": [],
                "count": 0,
                "count_scope": "ships 表当前取值分布（全部已入库船舶）",
            },
        )
        if raw not in entry["raw_values"]:
            entry["raw_values"].append(raw)
        entry["count"] += int(ship_count)
    entries = sorted(merged.values(), key=lambda item: (-item["count"], item["value"]))
    reserved = [entry for entry in entries if entry["value"].startswith("__")]
    return {
        "status": "ok" if entries else "no_data",
        "source": params.SOURCE,
        "total_ships": sum(entry["count"] for entry in entries),
        "ship_types": entries,
        "reserved": reserved,
        "count": len(entries),
        "limitations": list(CATALOG_LIMITATIONS),
    }
