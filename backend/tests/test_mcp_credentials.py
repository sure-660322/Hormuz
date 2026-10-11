"""Credential selection fails closed without exposing or persisting secrets."""
import pytest

from backend.mcp_server import credentials


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for prefix in ("MCP_DB", "AGENT_DB"):
        for suffix in ("PASSWORD", "PASSWORD_CREDENTIAL"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    yield
    for prefix in ("MCP_DB", "AGENT_DB"):
        credentials.os.environ.pop(f"{prefix}_PASSWORD", None)


def test_named_credential_only_enters_process_environment(monkeypatch):
    monkeypatch.setenv("MCP_DB_PASSWORD_CREDENTIAL", "test-profile")
    seen = []
    monkeypatch.setattr(credentials, "read_windows_credential",
                        lambda target: seen.append(target) or "fixture-secret")
    credentials.resolve_passwords()
    assert seen == ["test-profile"]
    assert credentials.os.environ["MCP_DB_PASSWORD"] == "fixture-secret"
    assert "AGENT_DB_PASSWORD" not in credentials.os.environ


def test_ambiguous_password_source_is_rejected_without_read(monkeypatch):
    monkeypatch.setenv("MCP_DB_PASSWORD", "fixture-secret")
    monkeypatch.setenv("MCP_DB_PASSWORD_CREDENTIAL", "test-profile")
    monkeypatch.setattr(credentials, "read_windows_credential",
                        lambda _: pytest.fail("Ambiguous source must not be read"))
    with pytest.raises(ValueError, match="not both") as error:
        credentials.resolve_passwords()
    assert "fixture-secret" not in str(error.value)
    assert "test-profile" not in str(error.value)


def test_missing_named_credential_does_not_set_password(monkeypatch):
    monkeypatch.setenv("MCP_DB_PASSWORD_CREDENTIAL", "test-profile")
    def unavailable(_):
        raise ValueError("Named Windows credential unavailable")
    monkeypatch.setattr(credentials, "read_windows_credential", unavailable)
    with pytest.raises(ValueError, match="unavailable"):
        credentials.resolve_passwords()
    assert "MCP_DB_PASSWORD" not in credentials.os.environ


def test_internal_sql_credential_is_never_read(monkeypatch):
    monkeypatch.setenv("AGENT_DB_PASSWORD_CREDENTIAL", "must-not-read")
    monkeypatch.setenv("MCP_SQL_ENABLED", "true")
    monkeypatch.setattr(credentials, "read_windows_credential",
                        lambda _: pytest.fail("External server must not read SQL credential"))
    credentials.resolve_passwords()
    assert "AGENT_DB_PASSWORD" not in credentials.os.environ


def test_explicit_environment_password_needs_no_native_api(monkeypatch):
    monkeypatch.setenv("MCP_DB_PASSWORD", "fixture-secret")
    monkeypatch.setattr(credentials, "read_windows_credential",
                        lambda _: pytest.fail("No named credential configured"))
    credentials.resolve_passwords()
    assert credentials.os.environ["MCP_DB_PASSWORD"] == "fixture-secret"


@pytest.mark.parametrize("target", ["", "x" * 257])
def test_invalid_credential_target_is_rejected(target):
    with pytest.raises(ValueError, match="unavailable"):
        credentials.read_windows_credential(target)
