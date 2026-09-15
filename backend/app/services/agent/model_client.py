"""DeepSeek（OpenAI 兼容 API）模型客户端薄封装。

密钥只从环境变量 DEEPSEEK_API_KEY 读取，绝不写入日志或异常消息。
超时与重试参数集中在本模块。
"""
import os

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

# 单次模型请求超时（秒）；整体 60 秒预算由 runner 控制
MODEL_REQUEST_TIMEOUT = 30.0
# 网络类错误（连接失败/超时/限流）的最大重试次数
MAX_NETWORK_RETRIES = 2


class AgentConfigError(RuntimeError):
    """模型配置缺失或不合法（如未设置 API key）。"""


class AgentModelUnavailableError(RuntimeError):
    """模型服务不可达或持续返回错误。"""


def build_client() -> OpenAI:
    """从环境变量构造 OpenAI 兼容客户端；key 缺失时抛 AgentConfigError。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise AgentConfigError("未配置 DEEPSEEK_API_KEY，无法使用智能体模型服务")
    base_url = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=MODEL_REQUEST_TIMEOUT,
        max_retries=MAX_NETWORK_RETRIES,
    )


def default_model() -> str:
    return os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"


def is_network_error(exc: Exception) -> bool:
    """连接/超时/限流类错误：可视为模型不可用，映射为 AGENT_UNAVAILABLE。"""
    return isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError))


__all__ = [
    "AgentConfigError",
    "AgentModelUnavailableError",
    "build_client",
    "default_model",
    "is_network_error",
    "MODEL_REQUEST_TIMEOUT",
]
