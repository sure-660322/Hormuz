# schemas_agent.py：智能体 /agent/analyze 的请求与响应模型
# 字段对齐 docs/agent_integration.md「预设响应与错误」一节（契约 v4）。
# 与 schemas.py 分离：该文件随智能体契约演进，不动现有接口模型。
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "3"
# 多轮 history 携带上限，与 backend/app/services/agent/langchain_runner.py 的 MAX_HISTORY_TURNS 一致
MAX_HISTORY_TURNS = 10
MAX_TURN_LENGTH = 2000


class AgentTurn(BaseModel):
    """一轮历史对话（role + content），由前端在追问时携带，最多最近 MAX_HISTORY_TURNS 轮。"""

    role: Literal["user", "assistant"]
    content: str  # 去除首尾空白后 1–2000 字符

    @field_validator("content")
    @classmethod
    def content_trimmed_length(cls, value: str) -> str:
        trimmed = value.strip()
        if not 1 <= len(trimmed) <= MAX_TURN_LENGTH:
            raise ValueError(f"content 去除首尾空白后须为 1–{MAX_TURN_LENGTH} 字符")
        return trimmed


class AgentAnalyzeRequest(BaseModel):
    question: str  # 必填，去除首尾空白后 1–2000 字符
    closure_at: datetime | None = None  # 可省略，须带时区，统一 UTC
    end_at: datetime | None = None
    history: list[AgentTurn] | None = None  # 多轮对话历史，可省略（单轮问答）

    @field_validator("question")
    @classmethod
    def question_trimmed_length(cls, value: str) -> str:
        trimmed = value.strip()
        if not 1 <= len(trimmed) <= 2000:
            raise ValueError("question 去除首尾空白后须为 1–2000 字符")
        return trimmed

    @field_validator("closure_at", "end_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("时间字段必须包含显式时区（统一 UTC）")
        return value

    @field_validator("history")
    @classmethod
    def history_within_limit(cls, value: list[AgentTurn] | None) -> list[AgentTurn] | None:
        if value is not None and len(value) > MAX_HISTORY_TURNS:
            raise ValueError(f"history 最多携带 {MAX_HISTORY_TURNS} 轮")
        return value


class AgentContext(BaseModel):
    batch: str  # 当前模拟批次说明
    ship_data_source: str  # 恒为 simulation
    closure_at: datetime
    end_at: datetime
    closure_source: str  # 封锁时间来源（默认假设 / 用户输入）
    passage_rule: str  # 通行规则版本与门线口径出处
    schema_version: str  # 契约版本，本版为 "3"


class AgentShip(BaseModel):
    ship_id: int
    name: str
    passage_count: int


class AgentPositionFix(BaseModel):
    recorded_at: datetime
    longitude: float
    latitude: float


class AgentEvidence(BaseModel):
    evidence_id: str  # P1/P2…
    ship_id: int
    direction: str
    start_fix: AgentPositionFix
    completion_fix: AgentPositionFix
    observed_completion_at: datetime


class AgentQuerySummary(BaseModel):
    position_count: int
    matched_ship_count: int
    passage_count: int
    uncertain_candidate_count: int
    coverage_start: datetime | None
    coverage_end: datetime | None
    truncated: bool


class AgentAnalyzeResponse(BaseModel):
    schema_version: str
    request_id: str
    status: Literal["ok", "no_data", "partial", "needs_clarification", "refused"]
    answer: str
    context: AgentContext
    ships: list[AgentShip]
    evidence: list[AgentEvidence]
    query_summary: AgentQuerySummary | None  # needs_clarification 或非通行工具时为 null
    tools_used: list[str]  # 本次实际执行的工具名（执行顺序去重）
    results: dict[str, Any]  # 各工具的结构化结果（按服务端 call_id），供前端展示与追溯
    limitations: list[str]
    clarification: str | None  # 非澄清状态为空
    map_actions: list["AgentMapAction"] = Field(default_factory=list)


class AgentMapAction(BaseModel):
    type: Literal["ship_track", "event"]
    trigger: Literal["automatic", "suggested"]
    ship_id: int | None = None
    event_id: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    source: Literal["nnu_ais", "news"]


class AgentErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
