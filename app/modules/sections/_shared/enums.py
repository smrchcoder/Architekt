"""Shared enums for section schemas.

These enums are used by section schemas that previously used raw ``str``
for categorical fields. Using ``str, Enum`` subclasses ensures type safety
while serializing as plain strings in JSON (backward compatible).
"""

from __future__ import annotations
from enum import Enum


class Severity(str, Enum):
    """Severity level for problem signals."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class TradeoffCategory(str, Enum):
    """Category classification for design tradeoffs."""
    PERFORMANCE = "performance"
    CONSISTENCY = "consistency"
    COST = "cost"
    COMPLEXITY = "complexity"
    RELIABILITY = "reliability"
    SECURITY = "security"
    OTHER = "other"
