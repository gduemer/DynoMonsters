"""Wear and Tear algorithm for DynoMonsters.

Parts lose condition over time through racing.  Condition is a float in
[0.0, 1.0] where 1.0 is brand-new and 0.0 is completely worn out.

Rules
-----
- Each race reduces condition by ``WEAR_PER_RACE`` (default 1 %).
- Condition is clamped to [0.0, 1.0] and never goes negative.
- All functions are pure and deterministic (no randomness).
- Non-finite or out-of-range inputs raise ``ValueError``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEAR_PER_RACE: float = 0.01   # 1 % condition loss per race
MIN_CONDITION: float = 0.0
MAX_CONDITION: float = 1.0


# ---------------------------------------------------------------------------
# Core wear functions
# ---------------------------------------------------------------------------


def apply_race_wear(condition: float, races: int = 1) -> float:
    """Return the new condition after *races* races.

    Parameters
    ----------
    condition:
        Current condition in [0.0, 1.0].
    races:
        Number of races to apply wear for (default 1).

    Returns
    -------
    float
        New condition, clamped to [0.0, 1.0].

    Raises
    ------
    ValueError
        If *condition* is non-finite, out of range, or *races* is negative.
    """
    if not isinstance(condition, (int, float)) or not math.isfinite(condition):
        raise ValueError(
            f"condition must be a finite number, got {condition!r}"
        )
    if condition < MIN_CONDITION or condition > MAX_CONDITION:
        raise ValueError(
            f"condition must be in [{MIN_CONDITION}, {MAX_CONDITION}], "
            f"got {condition}"
        )
    if not isinstance(races, int) or races < 0:
        raise ValueError(
            f"races must be a non-negative integer, got {races!r}"
        )

    new_condition = condition - WEAR_PER_RACE * races
    result = max(MIN_CONDITION, new_condition)

    logger.debug(
        "Wear applied: condition %.4f → %.4f (races=%d)",
        condition,
        result,
        races,
    )
    return result


def apply_wear_to_parts(
    parts: list[dict[str, Any]],
    races: int = 1,
) -> list[dict[str, Any]]:
    """Apply race wear to every part in *parts*.

    Each part dict must have a ``"condition"`` key with a float value in
    [0.0, 1.0].  A new list of dicts is returned; the originals are not
    mutated.

    Parameters
    ----------
    parts:
        List of part dicts, each containing at least ``{"condition": float}``.
    races:
        Number of races to apply (default 1).

    Returns
    -------
    list[dict]
        New list of part dicts with updated ``"condition"`` values.

    Raises
    ------
    ValueError
        If any part's condition is invalid or *races* is negative.
    """
    if not isinstance(races, int) or races < 0:
        raise ValueError(
            f"races must be a non-negative integer, got {races!r}"
        )

    result: list[dict[str, Any]] = []
    for i, part in enumerate(parts):
        updated = dict(part)
        raw_condition = part.get("condition", MAX_CONDITION)
        try:
            condition = float(raw_condition)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Part at index {i} has non-numeric condition: {raw_condition!r}"
            ) from exc
        updated["condition"] = apply_race_wear(condition, races)
        result.append(updated)

    return result


def races_until_worn_out(condition: float) -> int:
    """Return the number of races until condition reaches 0.0.

    Parameters
    ----------
    condition:
        Current condition in [0.0, 1.0].

    Returns
    -------
    int
        Number of full races remaining before the part is worn out.
        Returns 0 if already at 0.0.
    """
    if not isinstance(condition, (int, float)) or not math.isfinite(condition):
        raise ValueError(
            f"condition must be a finite number, got {condition!r}"
        )
    if condition < MIN_CONDITION or condition > MAX_CONDITION:
        raise ValueError(
            f"condition must be in [{MIN_CONDITION}, {MAX_CONDITION}], "
            f"got {condition}"
        )
    if condition <= MIN_CONDITION:
        return 0
    return math.floor(condition / WEAR_PER_RACE)
