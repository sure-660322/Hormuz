"""LC-02：轻量知识库与多轮指代的离线自动测试。

不连接真实数据库、不调用真实模型；模型用 backend.tests.fake_llm 的脚本化假模型。
"""
from backend.app.services.agent.knowledge_base import reload_knowledge, search_knowledge
from backend.app.services.agent.langchain_runner import run_lc_agent
from backend.tests.fake_llm import ScriptedFakeLLM, tool_call as _tool_call


# ------------------------------------------------------------ 知识库检索
def test_knowledge_search_finds_passage_rules():
    reload_knowledge()
    matches = search_knowledge("海峡完整通行怎么判定")
    assert matches
    top_sources = {match["source"] for match in matches}
    assert "passage_rules" in top_sources
    assert all(match["content"] for match in matches)


def test_knowledge_search_data_semantics():
    reload_knowledge()
    matches = search_knowledge("模拟船和真实新闻是什么关系")
    assert any(match["source"] == "data_semantics" for match in matches)


def test_knowledge_search_no_match_returns_empty():
    reload_knowledge()
    assert search_knowledge("") == []
    # 与项目完全无关且无任何命中的词
    assert search_knowledge("zzzzqqqqxxxx") == []


def test_knowledge_search_limits_to_five():
    reload_knowledge()
    matches = search_knowledge("数据 船舶 事件 模拟")
    assert len(matches) <= 5


# ------------------------------------------------------------ 知识库作为工具被调用
def test_agent_uses_knowledge_tool_for_project_question():
    llm = ScriptedFakeLLM(script=[
        _tool_call("search_project_knowledge", {"query": "地图上的船是真实 AIS 吗"}),
        "地图上的船舶与船位是教学模拟数据，不是真实 AIS；events/news 是真实报道聚合，"
        "两者相互独立，不能按船名认定为同一实体。",
    ])
    outcome = run_lc_agent(None, "地图上的船是真的吗", llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["search_project_knowledge"]
    envelope = outcome["results"]["call_001"]
    assert envelope["tool_name"] == "search_project_knowledge"
    assert envelope["count"] >= 1
    assert any("data_semantics" == m["source"] for m in envelope["matches"])
    assert "模拟" in outcome["answer"]


def test_agent_uses_knowledge_tool_for_capability_boundary():
    llm = ScriptedFakeLLM(script=[
        _tool_call("search_project_knowledge", {"query": "智能体能力边界"}),
        "我没有实时 AIS 或天气等外部实时数据工具，不能回答当前真实海上有多少船；"
        "项目只有历史教学模拟批次。",
    ])
    outcome = run_lc_agent(None, "现在海上有几艘船", llm=llm)
    assert outcome["tools_used"] == ["search_project_knowledge"]
    assert "不能" in outcome["answer"]


# ------------------------------------------------------------ 多轮指代
def test_pronoun_followup_continues_with_history_and_tool():
    """「它」指代上一轮船只：模型结合 history 调用业务工具核对。"""
    llm = ScriptedFakeLLM(script=[
        _tool_call("search_ships", {"keyword": "SIM V2 油轮 004"}),
        "SIM V2 油轮 004 的 ship_id 是 4。",
        _tool_call("get_ship_track", {"ship_id": 4}),
        "它（SIM V2 油轮 004，ship_id=4）在默认封锁窗口内共有 12 条轨迹报位。",
    ])
    first = run_lc_agent(None, "SIM V2 油轮 004 的船 ID 是多少？", llm=llm)
    assert first["tools_used"] == ["search_ships"]
    second = run_lc_agent(
        None,
        "它的轨迹有多少条报位？",
        history=[{"role": "user", "content": "SIM V2 油轮 004 的船 ID 是多少？"},
                 {"role": "assistant", "content": first["answer"]}],
        llm=llm,
    )
    assert second["tools_used"] == ["get_ship_track"]
    assert "报位" in second["answer"]
    # 两次问答各自独立记录工具结果
    assert len(second["results"]) == 1


def test_knowledge_result_is_json_serializable():
    import json

    from backend.app.services.agent.serialization import to_jsonable

    llm = ScriptedFakeLLM(script=[
        _tool_call("search_project_knowledge", {"query": "通行规则"}),
        "完整通行按门线口径判定。",
    ])
    outcome = run_lc_agent(None, "怎么判定通过海峡？", llm=llm)
    json.dumps(to_jsonable(outcome), ensure_ascii=False)
