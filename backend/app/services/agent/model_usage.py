"""Request-scoped metadata-only logs; no prompts, credentials or tool data."""
import json
import logging
from threading import RLock

from langchain_core.callbacks import BaseCallbackHandler

# Inherit Uvicorn's INFO handler in the normal documented launch command.
logger = logging.getLogger("uvicorn.error.agent_usage")


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class ModelUsageRecorder(BaseCallbackHandler):
    def __init__(self, request_id: str):
        self.request_id = request_id
        self.calls = {}
        self.lock = RLock()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        with self.lock:
            self.calls.setdefault(str(run_id), {"status": "pending"})

    def on_llm_end(self, response, *, run_id, **kwargs):
        with self.lock:
            key = str(run_id)
            if self.calls.get(key, {}).get("status") == "completed":
                return
            message = response.generations[0][0].message if response.generations and response.generations[0] else None
            usage = getattr(message, "usage_metadata", None) or {}
            raw = (getattr(message, "response_metadata", None) or {}).get("token_usage") or (response.llm_output or {}).get("token_usage") or {}
            details = usage.get("input_token_details") or {}
            self.calls[key] = {
                "status": "completed",
                "input_tokens": _count(usage.get("input_tokens", raw.get("prompt_tokens"))),
                "output_tokens": _count(usage.get("output_tokens", raw.get("completion_tokens"))),
                "cache_read_tokens": _count(details.get("cache_read", raw.get("prompt_cache_hit_tokens"))),
                "cache_miss_tokens": _count(raw.get("prompt_cache_miss_tokens")),
            }
            metadata = getattr(message, "response_metadata", None) or {}
            model = metadata.get("model_name") or metadata.get("model")
            logger.info("agent_model_usage %s", json.dumps({
                "request_id": self.request_id, "model_run_id": key,
                "model": model[:160] if isinstance(model, str) else None,
                "usage_status": "available" if all(self.calls[key][field] is not None for field in ("input_tokens", "output_tokens")) else "unavailable",
                **self.calls[key],
            }))

    def on_llm_error(self, error, *, run_id, **kwargs):
        with self.lock:
            key = str(run_id)
            if self.calls.get(key, {}).get("status") in {"completed", "failed"}:
                return
            self.calls[key] = {"status": "failed", "input_tokens": None,
                               "output_tokens": None, "cache_read_tokens": None,
                               "cache_miss_tokens": None}
            logger.info("agent_model_usage %s", json.dumps({
                "request_id": self.request_id, "model_run_id": key,
                **self.calls[key], "usage_status": "unavailable",
            }))

    def snapshot(self):
        with self.lock:
            rows = list(self.calls.values())
            totals = {}
            for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_miss_tokens"):
                values = [row.get(field) for row in rows]
                totals[field] = sum(values) if values and all(value is not None for value in values) else None
            return {"request_id": self.request_id, "model_calls": len(rows),
                    "network_attempts": None,
                    "usage_status": "available" if totals["input_tokens"] is not None and totals["output_tokens"] is not None else "unavailable",
                    **totals}

    def log_summary(self):
        logger.info("agent_request_usage %s", json.dumps(self.snapshot()))
