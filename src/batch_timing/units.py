"""All physical boundaries require quantities; internal time is seconds, activity Bq."""

import math
from tokenize import TokenError

import pint

ureg = pint.UnitRegistry()
Quantity = ureg.Quantity


def quantity(text: str) -> Quantity:
    if not isinstance(text, str):
        raise TypeError('Quantity must be a string with units, for example "30 min"')
    # Older tokenizer versions let Pint silently ignore this unsupported operator.
    if "@" in text:
        raise ValueError(f"Invalid quantity: {text!r}")
    try:
        result = ureg.Quantity(text)
    except (pint.PintError, TypeError, ValueError, SyntaxError, TokenError, ArithmeticError) as exc:
        raise ValueError(f"Invalid quantity: {text!r}") from exc
    return result


def magnitude(value: Quantity, unit: str, *, positive: bool = False) -> float:
    if not isinstance(value, pint.Quantity):
        raise TypeError(f"Expected a quantity convertible to {unit}")
    try:
        number = float(value.to(unit).magnitude)
    except (pint.PintError, TypeError) as exc:
        raise ValueError(f"Expected units convertible to {unit}") from exc
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(
            f"Expected a finite {'positive' if positive else 'nonnegative'} {unit} value"
        )
    return number
