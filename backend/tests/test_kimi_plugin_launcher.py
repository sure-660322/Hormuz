"""Windows plugin entry regression checks; no database or credentials accessed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


PLUGIN = Path(__file__).resolve().parents[2] / "plugins/kimi/personal/hormuz"
pytestmark = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("pwsh"),
                                reason="Windows PowerShell 7 plugin")


def launch(config_path, payload=b"", extra_env=None):
    manifest = json.loads((PLUGIN / "kimi.plugin.json").read_text(encoding="utf8"))
    server = manifest["mcpServers"]["hormuz"]
    return subprocess.run([server["command"], *server["args"]], cwd=PLUGIN,
                          env=dict(os.environ, HORMUZ_KIMI_CONFIG=str(config_path),
                                   **(extra_env or {})), input=payload,
                          capture_output=True, timeout=15)


def test_missing_config_is_generic_and_stdout_empty(tmp_path):
    result = launch(tmp_path / "absent.json")
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.strip() == b"Hormuz MCP launch failed; check the local runtime configuration."


@pytest.mark.parametrize("content", ["{", "null", '{"password":"fake-test-sentinel"}'])
def test_invalid_config_is_not_echoed(tmp_path, content):
    config = tmp_path / "config.json"
    config.write_text(content, encoding="utf8")
    result = launch(config)
    assert result.returncode == 1 and result.stdout == b""
    assert result.stderr.strip() == b"Hormuz MCP launch failed; check the local runtime configuration."


def test_raw_stdio_environment_isolation_and_exit_code(tmp_path):
    workspace = tmp_path / "workspace with spaces"
    module = workspace / "backend/mcp_server"
    module.mkdir(parents=True)
    (module / "__main__.py").write_text(
        "import os,sys\n"
        "assert os.environ['MCP_SQL_ENABLED']=='false'\n"
        "assert os.environ['MCP_DB_NAME']=='test_metadata_only'\n"
        "assert not any(k in os.environ for k in "
        "['DB_PASSWORD','MCP_DB_PASSWORD','AGENT_QUERY_FAKE','AGENT_DB_PASSWORD'])\n"
        "data=sys.stdin.buffer.read()\n"
        "sys.stdout.buffer.write(data);sys.stdout.buffer.flush()\n"
        "sys.stderr.buffer.write(b'fake-server-stderr\\n')\n"
        "sys.exit(17)\n", encoding="utf8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"python": sys.executable, "workspace": str(workspace),
        "database": {"user": "test", "credential": "unused-fake-target", "host": "127.0.0.1",
                     "port": "25432", "name": "test_metadata_only"}}), encoding="utf-8-sig")
    payload = (json.dumps({"text": "船舶" * 50000}, ensure_ascii=False) + "\n").encode()
    result = launch(config, payload, {"DB_PASSWORD": "fake", "MCP_DB_PASSWORD": "fake",
        "AGENT_QUERY_FAKE": "fake", "AGENT_DB_PASSWORD": "fake", "MCP_SQL_ENABLED": "true"})
    assert result.returncode == 17
    assert result.stdout == payload  # Exact bytes: no banner, Task result, encoding or line changes.
    assert result.stderr == b"fake-server-stderr\n"
