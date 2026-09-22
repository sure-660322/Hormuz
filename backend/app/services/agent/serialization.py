"""统一 JSON 序列化（LC-01）。

把工具结果与响应负载中的非 JSON 原生类型转换为可序列化值，覆盖：
Decimal、datetime/date、UUID、dataclass、pydantic BaseModel、SQLAlchemy Row、
dict/list/tuple/set。任何未知类型退化为 str，保证不产生未处理的 HTTP 500。

背景：data_health 的 median_gap_minutes 为 ::numeric（Decimal），
旧 _jsonable 未覆盖 Decimal，json.dumps 工具消息时抛出 TypeError 导致 500
（docs/agent_development_plan.md「当前已知缺陷」）。
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


def to_jsonable(value: Any) -> Any:
    """递归把 value 转换为 json.dumps 可处理的原生结构。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        # 与 query_analytics_executor._json_scalar 口径一致：整数值转 int，其余转 float
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, BaseModel):
        # python 模式保留原始类型（Decimal/datetime 等），交给下面的分支统一转换，
        # 保持 int/float 口径与 _json_scalar 一致
        return to_jsonable(value.model_dump(mode="python"))
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    # SQLAlchemy 1.4/2.0 Row 均暴露 _mapping
    mapping = getattr(value, "_mapping", None)
    if mapping is not None:
        return to_jsonable(dict(mapping))
    # 兜底：未知类型退化为 str，避免任何 500；结构化结果仍以工具自身字段为准
    return str(value)


def dumps_json(value: Any) -> str:
    """序列化任意工具结果为 JSON 字符串（供模型 observation 使用）。"""
    import json

    return json.dumps(to_jsonable(value), ensure_ascii=False)
