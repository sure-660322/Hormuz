# schemas_agent.py：智能体 /agent/analyze 的请求与响应模型
# 字段对齐 docs/agent_integration.md「预设响应与错误」一节（契约 v2）。
# 与 schemas.py 分离：该文件随智能体契约演进，不动现有接口模型。
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class AgentAnalyzeRequest(BaseModel):
    question: str  # 必填，去除首尾空白后 1–2000 字符
    closure_at: datetime | None = None  # 可省略，须带时区，统一 UTC
    end_at: datetime | None = None

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


class AgentContext(BaseModel):
    batch: str  # 当前模拟批次说明
    ship_data_source: str  # 恒为 simulation
    closure_at: datetime
    end_at: datetime
    closure_source: str  # 封锁时间来源（默认假设 / 用户输入）
    passage_rule: str  # 通行规则版本与门线口径出处
    schema_version: str  # 契约版本，本版为 "2"


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
    status: str  # ok / no_data / partial / needs_clarification
    answer: str
    context: AgentContext
    ships: list[AgentShip]
    evidence: list[AgentEvidence]
    query_summary: AgentQuerySummary | None  # needs_clarification 时为 null
    limitations: list[str]
    clarification: str | None  # 非澄清状态为空


class AgentErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
