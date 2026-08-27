"""Security-focused regression tests."""

import pytest
from fastapi.testclient import TestClient


def test_admin_key_enforced_when_configured(monkeypatch):
    from backend.core.config import get_settings
    from backend.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    monkeypatch.setenv("SEED_TASKS", "20")
    with TestClient(create_app()) as client:
        assert client.get("/api/admin/diagnostics").status_code == 401
        ok = client.get("/api/admin/diagnostics", headers={"x-admin-key": "s3cret"})
        assert ok.status_code == 200
        task_id = client.get("/api/tasks?limit=1").json()["items"][0]["task_id"]
        assert client.get(f"/api/tasks/{task_id}/ground-truth").status_code == 401
    get_settings.cache_clear()
    monkeypatch.delenv("ADMIN_API_KEY")


def test_settings_never_expose_secrets(monkeypatch):
    from backend.core.config import Settings

    s = Settings(admin_api_key="top-secret", model_api_key="sk-abc",
                 bittensor_wallet_name="w", bittensor_hotkey_name="h")
    blob = str(s.public_dict())
    assert "top-secret" not in blob and "sk-abc" not in blob
    assert s.public_dict()["model_backend_configured"] is True


def test_production_rejects_wildcard_cors():
    from backend.core.config import Settings

    s = Settings(environment="production", cors_origins="*")
    with pytest.raises(ValueError):
        _ = s.cors_origin_list


def test_debug_endpoints_disabled_in_production():
    from backend.core.config import Settings

    assert Settings(environment="production",
                    enable_debug_endpoints=True).debug_endpoints_enabled is False


def test_rate_limit_returns_429(monkeypatch):
    from backend.core.config import get_settings
    from backend.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setenv("SEED_TASKS", "20")
    with TestClient(create_app()) as client:
        codes = [client.get("/api/network/stats").status_code for _ in range(12)]
        assert 429 in codes
    get_settings.cache_clear()
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE")


def test_model_backend_never_returns_the_key(monkeypatch):
    from subnet.miner.model import OpenAICompatibleBackend

    monkeypatch.setenv("MODEL_API_KEY", "sk-should-not-leak")
    backend = OpenAICompatibleBackend()
    assert backend.configured is True
    assert "sk-should-not-leak" not in repr(backend)
    assert "sk-should-not-leak" not in str(backend.__dict__.get("model", ""))
    # the key is only ever used as an Authorization header, never surfaced
    out = backend.complete.__doc__ or ""
    assert "sk-" not in out


def test_no_secrets_in_repository():
    """Fails if a real-looking key is committed anywhere in the tree."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    pattern = re.compile(r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
    skip = {"node_modules", ".git", ".next", "__pycache__", "dist", "build"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".json", ".yml", ".yaml",
                               ".env", ".example", ".md"}:
            continue
        text = path.read_text(errors="ignore")
        assert not pattern.search(text), f"possible secret committed in {path}"
