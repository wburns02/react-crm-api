"""Cross-source deduplication and merge logic.

When the same address exists in multiple sources, fields are merged
by priority rather than overwritten blindly. Each field has a priority
list (defined in types.FIELD_PRIORITY) that determines which source wins.
"""

from __future__ import annotations

from typing import Any

from .quality import compute_quality_score
from .types import FIELD_PRIORITY, NormalizedPermit


def _source_key(source_portal_code: str) -> str:
    """Extract the adapter name from a source_portal_code.

    e.g. "mgo_ossf_williamson" → "mgo"
         "sss_travis_tx" → "sss"
         "tnr_travis_tx" → "tnr"
         "ocr_guadalupe_county_tx" → "ocr"
    """
    prefix = source_portal_code.split("_")[0]
    if prefix in ("mgo", "sss", "tnr", "ocr"):
        return prefix
    return source_portal_code


class Deduplicator:
    """Cross-source merge: group by address_hash, pick richest fields."""

    def __init__(self) -> None:
        self._groups: dict[str, list[NormalizedPermit]] = {}
        self.total_input = 0
        self.total_merged = 0

    def add(self, permit: NormalizedPermit) -> None:
        """Add a permit to the dedup buffer."""
        key = permit.get("address_hash", "")
        if not key:
            return
        self._groups.setdefault(key, []).append(permit)
        self.total_input += 1

    def add_all(self, permits: list[NormalizedPermit]) -> None:
        """Add multiple permits."""
        for p in permits:
            self.add(p)

    def merge(self) -> list[NormalizedPermit]:
        """Merge all groups and return deduplicated permit list.

        For single-source addresses, returns the permit as-is.
        For multi-source addresses, merges fields by priority.
        """
        results: list[NormalizedPermit] = []

        for _hash, group in self._groups.items():
            if len(group) == 1:
                results.append(group[0])
            else:
                merged = self._merge_group(group)
                results.append(merged)
                self.total_merged += 1

        return results

    def _merge_group(self, group: list[NormalizedPermit]) -> NormalizedPermit:
        """Merge permits from different sources for the same address.

        Strategy:
        1. Start with the highest-quality-score record as the base.
        2. For each field with a priority list, pick from highest-priority
           source that has a non-None value.
        3. Merge raw_data dicts (later sources supplement, not overwrite).
        """
        # Sort by quality score descending — best record is base
        group.sort(key=lambda p: p.get("quality_score", 0), reverse=True)
        base = dict(group[0])  # shallow copy

        # Index by source
        by_source: dict[str, NormalizedPermit] = {}
        for p in group:
            src = _source_key(p.get("source_portal_code", ""))
            # Keep highest-quality record per source
            if src not in by_source or p.get("quality_score", 0) > by_source[src].get(
                "quality_score", 0
            ):
                by_source[src] = p

        # Merge prioritized fields
        for field, priority in FIELD_PRIORITY.items():
            best_value = None
            for src in priority:
                record = by_source.get(src)
                if record and record.get(field) is not None:
                    best_value = record[field]
                    break
            if best_value is not None:
                base[field] = best_value

        # Merge raw_data from all sources
        merged_raw: dict[str, Any] = {}
        for p in group:
            raw = p.get("raw_data") or {}
            for k, v in raw.items():
                if k not in merged_raw and v is not None:
                    merged_raw[k] = v

        # Track which sources contributed
        sources = sorted({
            _source_key(p.get("source_portal_code", ""))
            for p in group
        })
        merged_raw["merged_sources"] = sources
        merged_raw["merge_count"] = len(group)
        base["raw_data"] = merged_raw

        # Use the richest source_portal_code (from highest-priority source)
        # that contributed the most fields
        base["source_portal_code"] = group[0].get("source_portal_code", "")

        # Recompute quality score after merge
        base["quality_score"] = compute_quality_score(base)
        base["raw_data"]["quality_score"] = base["quality_score"]

        return base  # type: ignore[return-value]

    @property
    def stats(self) -> dict[str, int]:
        single = sum(1 for g in self._groups.values() if len(g) == 1)
        multi = sum(1 for g in self._groups.values() if len(g) > 1)
        return {
            "total_input": self.total_input,
            "unique_addresses": len(self._groups),
            "single_source": single,
            "multi_source": multi,
            "output_count": len(self._groups),
        }
