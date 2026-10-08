"""Issue #47 回归：analysis_actions 判别联合（通行 + 区域动作共存过响应模型）。

背景：#40/#41 合并时 AgentAnalysisAction 两个成员被写进同一类，
passage_analysis 动作经 AgentAnalyzeResponse 校验直接 500；
修复后两类动作按 type 判别共存，HTTP 契约不再 500。
"""
from datetime import datetime, timezone

from backend.app.schemas_agent import (
    AgentAnalyzeResponse,
    AgentAreaAnalysisAction,
    AgentPassageAnalysisAction,
)

_CONTEXT = {
    "batch": "测试批次",
    "ship_data_source": "nnu_ais",
    "closure_at": datetime(2026, 2, 28, 15, 0, tzinfo=timezone.utc),
    "end_at": datetime(2026, 2, 28, 16, 0, tzinfo=timezone.utc),
    "closure_source": "默认假设",
    "passage_rule": "strait-gates-v1+stats-2026-10-07",
    "schema_version": "4",
}

_PASSAGE_ACTION = {
    "type": "passage_analysis",
    "trigger": "suggested",
    "query": {"mode": "compare", "a_start_at": "2026-02-25T00:00:00+00:00"},
    "summary": {"window": {"passage_count": 1}},
}

_AREA_ACTION = {
    "type": "area_activity",
    "trigger": "suggested",
    "mode": "activity",
    "query": {"start_at": "2026-02-28T00:00:00+00:00"},
    "summary": {"visit_count": 2},
    "tool": "query_area_ship_activity",
    "call_id": "call_001",
}


def _payload(actions: list[dict]) -> dict:
    return {
        "schema_version": "4",
        "request_id": "req-test",
        "status": "ok",
        "answer": "回答",
        "context": _CONTEXT,
        "ships": [],
        "evidence": [],
        "query_summary": None,
        "tools_used": [],
        "results": {},
        "limitations": [],
        "clarification": None,
        "analysis_actions": actions,
    }


def test_passage_action_survives_response_model():
    response = AgentAnalyzeResponse(**_payload([_PASSAGE_ACTION]))
    assert len(response.analysis_actions) == 1
    action = response.analysis_actions[0]
    assert isinstance(action, AgentPassageAnalysisAction)
    assert action.type == "passage_analysis"
    assert action.query["mode"] == "compare"


def test_area_action_survives_response_model():
    response = AgentAnalyzeResponse(**_payload([_AREA_ACTION]))
    action = response.analysis_actions[0]
    assert isinstance(action, AgentAreaAnalysisAction)
    assert action.mode == "activity"
    assert action.tool == "query_area_ship_activity"


def test_mixed_actions_coexist_in_order():
    response = AgentAnalyzeResponse(**_payload([_PASSAGE_ACTION, _AREA_ACTION]))
    assert [a.type for a in response.analysis_actions] == [
        "passage_analysis", "area_activity",
    ]
