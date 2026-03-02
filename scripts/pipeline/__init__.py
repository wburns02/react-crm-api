"""Unified Permit Data Pipeline — One True Source.

Replaces 8 separate ETL scripts with a modular pipeline:
  Source Adapters → Normalize → Enrich (parcel) → Dedup/Merge → API Batch
"""

__version__ = "1.0.0"
