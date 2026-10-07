"""POST /agent/analyze：智能体问答接口（契约 v4，LC-01 起由 LangChain Agent 驱动）。

错误体统一为 detail 对象 {code, message, request_id}，对齐契约「预设响应与错误」。
编排位于 services/agent/langchain_runner.py；模型配置缺失或不可用映射 503。
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from openai import APITimeoutError, OpenAIError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas_agent import AgentAnalyzeRequest, AgentAnalyzeResponse
from backend.app.services.agent.config import DEFAULT_CLOSURE_AT, MAX_WINDOW
from backend.app.services.agent.langchain_runner import run_lc_agent
from backend.app.services.agent.model_client import AgentConfigError
from backend.app.services.agent.results import (
    AgentInvalidResponseError,
    AgentTimeoutError,
)
from backend.app.services.agent.serialization import to_jsonable
from backend.app.services.agent.query_analytics_executor import QueryExecutionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _error(status_code: int, code: str, message: str, request_id: str):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "request_id": request_id},
    )


@router.post("/analyze", response_model=AgentAnalyzeResponse)
def analyze(
    request: AgentAnalyzeRequest,
    db: Session = Depends(get_db),
):
    request_id = str(uuid.uuid4())

    # 请求时间窗口的二次校验（查询层同样校验；此处直接拒绝，不与模型协商非法窗口）
    closure_at = request.closure_at or DEFAULT_CLOSURE_AT
    end_at = request.end_at or (closure_at + MAX_WINDOW)
    if not closure_at < end_at:
        _error(422, "INVALID_REQUEST", "end_at 必须晚于 closure_at", request_id)
    if end_at - closure_at > MAX_WINDOW:
        _error(422, "INVALID_REQUEST", "查询窗口不能超过 24 小时", request_id)

    try:
        outcome = run_lc_agent(
            db,
            question=request.question,
            closure_at=request.closure_at,
            end_at=request.end_at,
            history=[turn.model_dump() for turn in request.history] if request.history else None,
            request_id=request_id,
            map_context=request.map_context.model_dump() if request.map_context else None,
            area_context=request.area_context.model_dump() if request.area_context else None,
        )
    except AgentTimeoutError as exc:
        _error(504, "AGENT_TIMEOUT", str(exc), request_id)
    except AgentInvalidResponseError as exc:
        _error(502, "AGENT_INVALID_RESPONSE", str(exc), request_id)
    except AgentConfigError as exc:
        _error(503, "AGENT_UNAVAILABLE", str(exc), request_id)
    except ValueError as exc:
        _error(422, "INVALID_REQUEST", str(exc), request_id)
    except QueryExecutionError as exc:
        _error(exc.http_status, exc.code, exc.public_message, request_id)
    except SQLAlchemyError:
        logger.exception("agent query failed request_id=%s", request_id)
        _error(500, "DATA_QUERY_FAILED", "数据查询失败", request_id)
    except APITimeoutError as exc:
        _error(504, "AGENT_TIMEOUT", str(exc), request_id)
    except OpenAIError as exc:
        # 模型服务错误（连接失败/欠费/限流等）：不泄露连接与密钥细节
        logger.warning("model unavailable request_id=%s type=%s", request_id, type(exc).__name__)
        _error(503, "AGENT_UNAVAILABLE", "模型服务当前不可用", request_id)

    payload = to_jsonable(outcome)
    payload["request_id"] = request_id
    return AgentAnalyzeResponse(**payload)
