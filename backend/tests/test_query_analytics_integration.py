"""受限 SQL 的 HTTP 契约测试（LC-04 清理后保留项）。

旧版「模拟旧消息循环」的测试已在 LC-04 按方案 §7 移除，等价场景由
test_agent_sql_tools.py（execute_sql 拒绝关闭/语法修复/假执行器）和
test_agent_expressions.py（多表达矩阵）覆盖；SQL 策略/执行器专项测试
见 test_query_analytics_policy.py / test_query_analytics_executor.py。
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.routers import agent as agent_router
from backend.app.services.agent import langchain_runner
from backend.app.services.agent.query_analytics_executor import QueryExecutionError
from backend.tests.fake_llm import ScriptedFakeLLM


def _app():
    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = lambda: None
    return app


def test_http_vague_question_reaches_model(monkeypatch):
    """LC-03 移除固定短语分类后：「查一下」到达模型并由其自然追问。"""
    llm = ScriptedFakeLLM(script=["请说明要查询的对象、指标或时间范围。"])
    monkeypatch.setattr(langchain_runner, "build_llm", lambda: llm)

    response = TestClient(_app()).post("/agent/analyze", json={"question": "查一下"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "请说明" in response.json()["answer"]
    assert response.json()["results"] == {}


def test_http_maps_query_timeout_to_stable_error(monkeypatch):
    monkeypatch.setattr(
        agent_router,
        "run_lc_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            QueryExecutionError(
                status="timeout",
                code="AGENT_QUERY_TIMEOUT",
                public_message="query_analytics 查询超时",
                http_status=504,
                query_id="aq_http_timeout",
                query_executed=True,
            )
        ),
    )

    response = TestClient(_app()).post("/agent/analyze", json={"question": "统计新闻数量"})

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["code"] == "AGENT_QUERY_TIMEOUT"
    assert "aq_http_timeout" not in response.text
