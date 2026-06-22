from __future__ import annotations


class PublicFacingError(ValueError):
    """Exception with a message that is safe to return to API clients."""

