"""Minimal local-disk storage helper for HR artifacts.

This is a placeholder for Plan 1 — real S3 wiring lands later.  The storage
root is configurable via ``HR_STORAGE_ROOT`` so production can point at a
persistent mount (e.g. ``/mnt/win11/Fedora/hr-storage``) while tests use
``tmp_path``.  ``/tmp`` is tmpfs on the production host and must NOT be used
for real data — see CLAUDE.md (Storage Policy).

Seed-template fallback: ephemeral Railway containers wipe HR_STORAGE_ROOT on
every redeploy, which would otherwise orphan the seeded document-template
keys inserted by migration 100.  To keep those keys always resolvable, the
seed migration names them ``seed-<kind>-<hash>.pdf`` and this module falls
back to the bundled copies in ``app/hr/esign/pdfs/`` when the key starts
with ``seed-``.
"""
import os
import uuid
from pathlib import Path


_BUNDLED_PDF_DIR = Path(__file__).resolve().parents[1] / "esign" / "pdfs"


def _root() -> Path:
    return Path(os.getenv("HR_STORAGE_ROOT", "/var/tmp/hr-storage-dev"))


def _seed_key_to_bundled_path(key: str) -> Path | None:
    """Map a seed-<kind>-<hash>.pdf key back to the bundled PDF on disk.

    Returns None if `key` is not a seed key or no matching bundle exists.
    """
    if not key.startswith("seed-") or not key.endswith(".pdf"):
        return None
    # Strip prefix/suffix and the -<hash> tail.  e.g.
    #   seed-employment_agreement_2026-<hash>.pdf → employment_agreement_2026
    stem = key[len("seed-") : -len(".pdf")]
    kind = stem.rsplit("-", 1)[0] if "-" in stem else stem
    candidate = _BUNDLED_PDF_DIR / f"{kind}.pdf"
    return candidate if candidate.exists() else None


def save_bytes(data: bytes, suffix: str = ".bin") -> str:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4().hex}{suffix}"
    (root / key).write_bytes(data)
    return key


def read_bytes(key: str) -> bytes:
    primary = _root() / key
    if primary.exists():
        return primary.read_bytes()
    bundled = _seed_key_to_bundled_path(key)
    if bundled is not None:
        return bundled.read_bytes()
    # Let the caller see the original FileNotFoundError for non-seed keys.
    return primary.read_bytes()


def path_for(key: str) -> Path:
    primary = _root() / key
    if primary.exists():
        return primary
    bundled = _seed_key_to_bundled_path(key)
    if bundled is not None:
        return bundled
    return primary
