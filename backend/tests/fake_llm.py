"""测试共享辅助：脚本化假 ChatModel（LangChain create_agent 用）。

不连接真实数据库、不调用真实模型；供 LC 阶段各测试模块复用。
"""
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedFakeLLM(BaseChatModel):
    """按脚本顺序输出 AIMessage 的假模型；bind_tools 返回自身。

    script 耗尽后重复最后一条消息，模拟模型坚持同一回答。
    """

    script: list
    sleep_seconds: float = 0.0

    def _generate(self, messages, stop=None, **kwargs):
        if self.sleep_seconds:
            import time

            time.sleep(self.sleep_seconds)
        idx = min(getattr(self, "_calls", 0), len(self.script) - 1)
        self._calls = getattr(self, "_calls", 0) + 1
        message = self.script[idx]
        if not isinstance(message, AIMessage):
            message = AIMessage(content=message)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "scripted-fake"


def tool_call(name, args, call_id="call_1"):
    """构造一次工具调用的 AIMessage。"""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
    )
