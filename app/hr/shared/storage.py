"""Minimal local-disk storage helper for HR artifacts.

This is a placeholder for Plan 1 — real S3 wiring lands later.  The storage
root is configurable via ``HR_STORAGE_ROOT`` so production can point at a
persistent mount (e.g. ``/mnt/win11/Fedora/hr-storage``) while tests use
``tmp_path``.  ``/tmp`` is tmpfs on the production host and must NOT be used
for real data — see CLAUDE.md (Storage Policy).
"""
import os
import uuid
from pathlib import Path


def _root() -> Path:
    return Path(os.getenv("HR_STORAGE_ROOT", "/var/tmp/hr-storage-dev"))


def save_bytes(data: bytes, suffix: str = ".bin") -> str:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4().hex}{suffix}"
    (root / key).write_bytes(data)
    return key


def read_bytes(key: str) -> bytes:
    return (_root() / key).read_bytes()


def path_for(key: str) -> Path:
    return _root() / key
