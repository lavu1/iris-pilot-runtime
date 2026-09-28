"""Errors whose messages are safe to show without exposing connection credentials."""


class RuntimeContractError(Exception):
    """Configuration, source data, or persisted state violates a runtime contract."""
