"""LC-01：统一序列化与 Decimal HTTP 500 回归测试。

不连接真实数据库、不调用真实模型。
"""
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.app.services.agent import runner
from backend.app.services.agent.serialization import to_jsonable

UTC = timezone.utc


@dataclass
class _SampleDataclass:
    when: datetime
    amount: Decimal
    ident: uuid.UUID


class _SampleModel(BaseModel):
    name: str
    ratio: Decimal
    day: date


def test_to_jsonable_decimal_integral_becomes_int():
    assert to_jsonable(Decimal("17.0")) == 17
    assert isinstance(to_jsonable(Decimal("17.0")), int)


def test_to_jsonable_decimal_fractional_becomes_float():
    assert to_jsonable(Decimal("2.5")) == 2.5
    assert isinstance(to_jsonable(Decimal("2.5")), float)


def test_to_jsonable_datetime_date_uuid():
    moment = datetime(2026, 2, 28, 15, 0, 0, tzinfo=UTC)
    ident = uuid.uuid4()
    out = to_jsonable({"t": moment, "d": date(2026, 3, 1), "u": ident})
    assert out == {
        "t": "2026-02-28T15:00:00+00:00",
        "d": "2026-03-01",
        "u": str(ident),
    }


def test_to_jsonable_dataclass_and_pydantic():
    ident = uuid.uuid4()
    dc = _SampleDataclass(when=datetime(2026, 2, 28, tzinfo=UTC), amount=Decimal("17.0"), ident=ident)
    out = to_jsonable(dc)
    assert out["amount"] == 17
    assert out["ident"] == str(ident)
    model = _SampleModel(name="x", ratio=Decimal("0.5"), day=date(2026, 3, 1))
    out = to_jsonable(model)
    assert out["ratio"] == 0.5
    assert out["day"] == "2026-03-01"


def test_to_jsonable_sqlalchemy_row_mapping():
    row = SimpleNamespace(_mapping={"median_gap_minutes": Decimal("17.0")})
    assert to_jsonable(row) == {"median_gap_minutes": 17}


def test_to_jsonable_unknown_type_falls_back_to_str():
    assert to_jsonable(object()) .startswith("<object")


def test_runner_jsonable_matches_serialization():
    """旧 runner 的 _jsonable 已委托统一序列化（Decimal 不再 TypeError）。"""
    payload = {"median_gap_minutes": Decimal("17.0"), "ok": True}
    assert runner._jsonable(payload) == {"median_gap_minutes": 17, "ok": True}
    json.dumps(runner._jsonable(payload), ensure_ascii=False)  # 不抛 TypeError


# ---- Decimal 500 回归：完整响应可 JSON 序列化 ----
def test_full_outcome_with_decimal_is_json_safe():
    outcome = {
        "schema_version": "4",
        "status": "ok",
        "answer": "中位间隔 17 分钟",
        "results": {
            "call_001": {
                "call_id": "call_001",
                "tool_name": "get_data_health",
                "status": "ok",
                "sources": [{"median_gap_minutes": Decimal("17.0")}],
            }
        },
    }
    # 契约路径：先 _jsonable 再 json.dumps（旧实现在此抛 TypeError → HTTP 500）
    json.dumps(runner._jsonable(outcome), ensure_ascii=False)
