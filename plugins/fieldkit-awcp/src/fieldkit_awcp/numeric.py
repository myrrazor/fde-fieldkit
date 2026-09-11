"""Shared finite-number validation for untrusted numeric inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional


MAX_SAFE_INTEGER = 2**53 - 1


@dataclass(frozen=True)
class NumericValidationError(ValueError):
    """Sanitized numeric validation failure."""

    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


def finite_number(
    value: Any,
    *,
    field: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    require_safe_integer: bool = False,
) -> float:
    """Return a bounded finite float without coercing strings or booleans."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise NumericValidationError(field, "non_numeric")
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise NumericValidationError(field, "numeric_overflow") from exc
    if not math.isfinite(converted):
        raise NumericValidationError(field, "non_finite")
    if isinstance(value, int) and abs(value) > MAX_SAFE_INTEGER:
        raise NumericValidationError(field, "numeric_precision")
    if (
        require_safe_integer
        and isinstance(value, float)
        and value.is_integer()
        and abs(value) > MAX_SAFE_INTEGER
    ):
        raise NumericValidationError(field, "numeric_precision")
    if minimum is not None and converted < minimum:
        raise NumericValidationError(field, "below_minimum")
    if maximum is not None and converted > maximum:
        raise NumericValidationError(field, "above_maximum")
    return converted
