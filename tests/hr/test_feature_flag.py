import pytest
from app.hr.feature_flag import hr_module_enabled


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
