"""区域上下文解析（Lead 复核后的身份规则，issue #41 第二、三阶段）。

覆盖两点：
1. 请求未给区域 → 版本化默认区域；
2. 显式给 area_id=默认区域标识且四边界等于默认区域 → 仍按默认区域处理
   （否则智能体回显 area_id=custom，丢掉默认区身份，数字不变但身份错）。
"""
import pytest

from backend.app.services.area_activity import boundaries, params
from backend.app.services.area_activity.context import (
    area_context_payload,
    bounds_from_arguments,
    resolve_area_context,
    ship_type_values,
)

DEFAULT = {"west": 55.8, "south": 25.8, "east": 57.1, "north": 27.1}
CUSTOM = {"west": 55.9, "south": 25.9, "east": 57.0, "north": 27.0}


def test_missing_context_uses_versioned_default_area():
    ctx = resolve_area_context(None)
    assert ctx.is_default is True
    assert ctx.area_id == params.DEFAULT_AREA_ID
    assert ctx.version == params.DEFAULT_AREA_VERSION
    assert ctx.label == params.DEFAULT_AREA_NAME
    assert ctx.source == "default"


def test_default_bounds_with_default_area_id_stay_default():
    ctx = resolve_area_context({**DEFAULT, "area_id": params.DEFAULT_AREA_ID, "label": "面板当前区域"})
    assert ctx.is_default is True
    assert ctx.area_id == params.DEFAULT_AREA_ID
    assert ctx.version == params.DEFAULT_AREA_VERSION
    payload = area_context_payload(ctx)
    assert payload["area_id"] == params.DEFAULT_AREA_ID
    assert payload["is_default"] is True
    assert payload["west"] == 55.8 and payload["north"] == 27.1


def test_bounds_without_area_id_are_custom():
    ctx = resolve_area_context({**DEFAULT})
    assert ctx.is_default is False
    assert ctx.area_id == "custom"
    assert ctx.version is None


def test_custom_bounds_with_custom_id_are_custom():
    ctx = resolve_area_context({**CUSTOM, "area_id": "custom"})
    assert ctx.is_default is False
    assert ctx.area_id == "custom"
    assert ctx.bounds.west == 55.9


def test_partial_bounds_and_non_numeric_are_rejected():
    with pytest.raises(ValueError, match="同时给出"):
        resolve_area_context({"west": 55.8, "south": 25.8})
    with pytest.raises(ValueError, match="必须是数值"):
        resolve_area_context({**DEFAULT, "north": "27.1"})


def test_bounds_from_arguments_keeps_current_area_when_omitted():
    current = resolve_area_context(None)
    assert bounds_from_arguments(None, None, None, None, None, current) is current
    with pytest.raises(ValueError, match="同时给出"):
        bounds_from_arguments(55.8, None, None, None, None, current)
    replaced = bounds_from_arguments(**{k: v for k, v in CUSTOM.items()}, explicit_area_id="custom", current=current)
    assert replaced.is_default is False
    assert replaced.area_id == "custom"
    assert replaced.bounds.west == 55.9


def test_default_area_bounds_match_boundaries_helper():
    # 身份规则依赖「四边界与默认区域完全一致」，这里锁死两个来源不会漂移
    assert boundaries.default_bounds().as_dict() == {
        "south": DEFAULT["south"], "west": DEFAULT["west"],
        "north": DEFAULT["north"], "east": DEFAULT["east"],
    }


def test_ship_type_values_normalises_empty_and_whitespace():
    assert ship_type_values(None) is None
    assert ship_type_values([]) is None
    assert ship_type_values(["  ", ""]) is None
    assert ship_type_values([" 油轮 ", "货船"]) == ["油轮", "货船"]
