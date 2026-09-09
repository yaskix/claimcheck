"""claimcheck — a provenance gate for AI-assisted marketing copy."""

from .compose import compose
from .numbers import Quantity, extract, matches
from .store import Claim, Store, StoreError, load_store
from .validate import Finding, Report, check

__version__ = "0.1.0"

__all__ = [
    "Claim",
    "Finding",
    "Quantity",
    "Report",
    "Store",
    "StoreError",
    "check",
    "compose",
    "extract",
    "load_store",
    "matches",
]
