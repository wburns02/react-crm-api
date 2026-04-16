"""Regression tests for app/hr/shared/storage.py seed-key fallback.

On Railway, HR_STORAGE_ROOT lives in an ephemeral volume that is wiped on
every redeploy.  Migration 100 writes seeded templates with keys of the form
``seed-<kind>-<hash>.pdf`` and storage.read_bytes() must be able to resolve
those back to the bundled PDFs in app/hr/esign/pdfs/ even when the ephemeral
copy is gone.
"""
import pytest

from app.hr.shared import storage


@pytest.fixture(autouse=True)
def _empty_storage_root(tmp_path, monkeypatch):
    """Simulate a fresh container where HR_STORAGE_ROOT is empty."""
    monkeypatch.setenv("HR_STORAGE_ROOT", str(tmp_path))
    yield


def test_read_bytes_falls_back_to_bundled_pdf_for_seed_key():
    # Any seed key for one of the 5 bundled kinds should resolve.
    key = "seed-i9-deadbeef0123456789abcdef01234567.pdf"
    data = storage.read_bytes(key)
    assert data.startswith(b"%PDF"), "should return a real PDF"
    assert len(data) > 1000


def test_path_for_returns_bundled_path_when_not_in_storage():
    key = "seed-w4_2026-abc.pdf"
    p = storage.path_for(key)
    assert p.exists()
    assert p.name == "w4_2026.pdf"


def test_read_bytes_prefers_storage_root_when_file_present(tmp_path, monkeypatch):
    monkeypatch.setenv("HR_STORAGE_ROOT", str(tmp_path))
    key = "seed-i9-override.pdf"
    payload = b"%PDF-override\n"
    (tmp_path / key).write_bytes(payload)

    assert storage.read_bytes(key) == payload


def test_read_bytes_raises_for_unknown_non_seed_key():
    with pytest.raises(FileNotFoundError):
        storage.read_bytes("non-existent-xyz.pdf")
