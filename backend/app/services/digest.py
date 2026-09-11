"""Truncated hashes for values that must be correlated in logs but not shown."""
import hashlib


def fingerprint(value: str) -> str:
    """Return the first 12 hex characters of the SHA-256 of value."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]
