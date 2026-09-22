"""LC-03：受限 SQL Agent 工具（get_database_schema / check_sql / execute_sql）。

复用 SQL-03/04 安全底座（docs/query_analytics_contract.md）：
- 校验：query_analytics_policy.validate_query（SQLGlot 全树白名单，不执行）；
- 执行：query_analytics_executor.QueryAnalyticsExecutor（独立只读连接、
  SELECT-only、超时、结果上限、query_id），绝不使用主应用 Session。

工具仅在功能开关完整（ExecutorConfig.from_env 通过）时向模型暴露；
任何策略拒绝/超时都会关闭后续 execute_sql（state["sql_closed"]），
只有尚未执行的普通语法错误允许修正一次（retryable）。
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from backend.app.services.agent.query_analytics_executor import (
    ExecutorConfig,
    QueryAnalyticsExecutor,
    QueryExecutionError,
)
from backend.app.services.agent.query_analytics_policy import (
    QueryPolicyError,
    QuerySyntaxError,
    load_catalog,
    validate_query,
)
from backend.app.services.agent.serialization import to_jsonable

# 测试接缝：与 v4 runner.QUERY_ANALYTICS_EXECUTOR_FACTORY 同款
EXECUTOR_FACTORY = QueryAnalyticsExecutor.from_env

_CATALOG_PATH = None  # 使用 policy 模块默认 catalog 路径


def sql_tools_enabled() -> bool:
    """只决定是否向模型暴露 SQL 工具；启用后的完整配置仍由执行器 fail closed。"""
    try:
        return ExecutorConfig.from_env().enabled
    except QueryExecutionError:
        return False


def _schema_payload() -> dict:
    catalog = load_catalog()
    return {
        "status": "ok",
        "catalog_version": catalog["catalog_version"],
        "max_returned_rows": catalog.get("max_returned_rows"),
        "views": [
            {
                "name": view["name"],
                "data_scope": view["data_scope"],
                "row_limit": view["row_limit"],
                "limitations": view["limitations"],
                "columns": [
                    {
                        "name": column["name"],
                        "type": column["postgres_type"],
                        "description": column["description"],
                    }
                    for column in view["columns"]
                ],
            }
            for view in catalog["views"]
        ],
        "allowed_joins": catalog["allowed_joins"],
        "rules": [
            "仅允许单条 SELECT；关系必须使用 agent_data 全限定视图名",
            "条件值必须使用 :name 命名绑定参数，不得使用字面量绕过参数",
            "唯一批准 JOIN：v_news.event_id = v_events.event_id（INNER/LEFT）",
            "禁止任何写入、底表/系统目录访问和策略放宽尝试",
        ],
    }


def _check_payload(sql: str, params: list | None, purpose: str) -> dict:
    try:
        validated = validate_query(sql, params or [], purpose, catalog=load_catalog())
    except QueryPolicyError as exc:
        return {
            "status": "syntax_error" if isinstance(exc, QuerySyntaxError) else exc.code,
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
        }
    return {
        "status": "ok",
        "normalized_sql": validated.normalized_sql,
        "referenced_views": list(validated.referenced_views),
        "params": [param.name for param in validated.params],
        "message": "校验通过，可调用 execute_sql 执行；execute_sql 会再次校验并只读执行",
    }


def _execute_payload(
    sql: str,
    params: list | None,
    purpose: str,
    *,
    request_id: str,
    call_id: str,
) -> dict:
    executor = EXECUTOR_FACTORY()
    try:
        result = executor.execute(
            sql=sql,
            params=params or [],
            purpose=purpose,
            request_id=request_id,
            call_id=call_id,
        )
        return result.to_dict()
    finally:
        executor.dispose()


def make_sql_tools(*, request_id: str, state: dict) -> list[StructuredTool]:
    """构造三个受限 SQL 工具；执行/拒绝记录到 state（results、tools_used、sql_closed）。"""

    def _record(tool_name: str, payload: dict) -> str:
        state["call_sequence"] += 1
        call_id = f"call_{state['call_sequence']:03d}"
        envelope = to_jsonable({"call_id": call_id, "tool_name": tool_name, **payload})
        if tool_name not in state["tools_used"]:
            state["tools_used"].append(tool_name)
        state["results"][call_id] = envelope
        return json.dumps(envelope, ensure_ascii=False)

    class _SchemaArgs(BaseModel):
        pass

    class _CheckArgs(BaseModel):
        sql: str = Field(description="单条只读 SELECT；关系使用 agent_data 全限定名，条件值用 :name 参数")
        params: list | None = Field(default=None, description="命名绑定参数 [{name,type,value}]，可省略")
        purpose: str = Field(default="", description="查询用途说明（最多 500 字；不构成授权依据）")

    class _ExecuteArgs(BaseModel):
        sql: str = Field(description="已经过 check_sql 校验的单条只读 SELECT")
        params: list | None = Field(default=None, description="与 check_sql 一致的命名绑定参数")
        purpose: str = Field(default="", description="查询用途说明（最多 500 字；不构成授权依据）")

    def _get_database_schema() -> str:
        try:
            return _record("get_database_schema", _schema_payload())
        except QueryPolicyError as exc:
            return _record("get_database_schema", {
                "status": "error", "code": exc.code, "message": str(exc),
            })

    def _check_sql(sql: str, params: list | None = None, purpose: str = "") -> str:
        return _record("check_sql", _check_payload(sql, params, purpose))

    def _execute_sql(sql: str, params: list | None = None, purpose: str = "") -> str:
        if state.get("sql_closed"):
            return _record("execute_sql", {
                "status": "error", "code": "SQL_CLOSED",
                "message": "execute_sql 已因拒绝/超时/执行失败终止，不允许再次调用；"
                           "请基于已有结果回答，或改走业务工具。",
            })
        state["call_sequence"] += 1
        call_id = f"call_{state['call_sequence']:03d}"
        try:
            payload = _execute_payload(
                sql, params, purpose, request_id=request_id, call_id=call_id
            )
        except QueryExecutionError as exc:
            # 安全拒绝、超时或已执行的失败：关闭后续 execute_sql；
            # 尚未执行的普通语法错误（retryable）允许修正一次
            if not (exc.retryable and not exc.query_executed):
                state["sql_closed"] = True
            payload = {
                "status": exc.status,
                "code": exc.code,
                "message": exc.public_message,
                "query_id": exc.query_id,
                "query_executed": exc.query_executed,
                "retryable": exc.retryable,
            }
        envelope = to_jsonable({"call_id": call_id, "tool_name": "execute_sql", **payload})
        if "execute_sql" not in state["tools_used"]:
            state["tools_used"].append("execute_sql")
        state["results"][call_id] = envelope
        return json.dumps(envelope, ensure_ascii=False)

    return [
        StructuredTool.from_function(
            func=_get_database_schema,
            name="get_database_schema",
            description=(
                "返回受限分析 catalog：允许查询的 agent_data 语义视图、字段类型与业务说明、"
                "批准的 JOIN 和行数上限。生成任何统计 SQL 前必须先调用本工具"
            ),
            args_schema=_SchemaArgs,
        ),
        StructuredTool.from_function(
            func=_check_sql,
            name="check_sql",
            description=(
                "对候选 SQL 做只读策略校验（不执行、不触库）：返回规范化 SQL 或"
                "可理解的拒绝/语法原因。execute_sql 前应先通过本检查"
            ),
            args_schema=_CheckArgs,
        ),
        StructuredTool.from_function(
            func=_execute_sql,
            name="execute_sql",
            description=(
                "只执行通过策略校验的单条 SELECT（独立只读连接、超时、结果上限、query_id）。"
                "安全拒绝/超时/执行失败后本工具关闭，不得换写法重试；"
                "只有第一次尚未执行的普通语法错误可修正一次"
            ),
            args_schema=_ExecuteArgs,
        ),
    ]
