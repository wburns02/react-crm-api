import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.hr.feature_flag import hr_module_enabled
from app.hr.router import hr_router


def test_hr_module_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HR_MODULE_ENABLED", raising=False)
    assert hr_module_enabled() is False


def test_hr_module_enabled_when_true(monkeypatch):
    monkeypatch.setenv("HR_MODULE_ENABLED", "true")
    assert hr_module_enabled() is True


def test_hr_module_respects_falsy_values(monkeypatch):
    monkeypatch.setenv("HR_MODULE_ENABLED", "0")
    assert hr_module_enabled() is False
    monkeypatch.setenv("HR_MODULE_ENABLED", "false")
    assert hr_module_enabled() is False


def _build_gated_app(flag_on: bool) -> FastAPI:
    """Replicate the registration pattern used in app/main.py so we can test
    the gating logic without reloading the massive main module."""
    import os
    os.environ["HR_MODULE_ENABLED"] = "true" if flag_on else ""
    mini = FastAPI()
    if hr_module_enabled():
        mini.include_router(hr_router, prefix="/api/v2")
    return mini


@pytest.mark.asyncio
async def test_hr_router_not_registered_when_flag_off(monkeypatch):
    monkeypatch.delenv("HR_MODULE_ENABLED", raising=False)
    app = _build_gated_app(flag_on=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v2/hr/health")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_hr_router_registered_when_flag_on(monkeypatch):
    monkeypatch.setenv("HR_MODULE_ENABLED", "true")
    app = _build_gated_app(flag_on=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v2/hr/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "module": "hr"}


def test_main_wiring_uses_flag_check():
    """Sanity check: confirm app/main.py actually gates the HR include on the flag."""
    main_src = (__import__("pathlib").Path(__file__).resolve().parents[2] / "app" / "main.py").read_text()
    assert "hr_module_enabled()" in main_src
    assert "include_router(hr_router" in main_src
