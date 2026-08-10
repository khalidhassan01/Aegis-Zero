"""Typed error taxonomy for Aegis Zero.

Every failure mode in the system maps to exactly one of these. Nothing is
swallowed: callers either handle a specific subclass or let it propagate.
"""

from __future__ import annotations


class AegisError(Exception):
    """Base for every Aegis Zero failure."""

    retryable: bool = False

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        if not self.context:
            return self.message
        detail = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} ({detail})"


class ConfigError(AegisError):
    """Malformed or missing configuration."""


class ProviderError(AegisError):
    """An LLM provider failed."""


class ProviderTimeout(ProviderError):
    retryable = True


class ProviderRateLimited(ProviderError):
    retryable = True


class ProviderUnavailable(ProviderError):
    retryable = True


class AllProvidersFailed(ProviderError):
    """Every model in the fallback chain was exhausted."""


class ToolError(AegisError):
    """A tool failed during execution."""


class ToolNotFound(ToolError):
    pass


class ToolValidationError(ToolError):
    """Arguments did not satisfy the tool schema."""


class ToolTimeout(ToolError):
    retryable = True


class PolicyDenied(AegisError):
    """The policy engine refused an action. Never retryable."""


class ApprovalRequired(AegisError):
    """A human must approve before this action proceeds."""


class ApprovalDenied(AegisError):
    """A human explicitly refused."""


class MemoryFailure(AegisError):
    """Vector store / memory subsystem failure."""


# Backwards-compatible alias.
MemoryError_ = MemoryFailure


class BudgetExceeded(AegisError):
    """Token, cost, step, or wall-clock budget exhausted."""


class Cancelled(AegisError):
    """The run was cancelled cooperatively."""
