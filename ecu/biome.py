"""Biome modifier logic for DynoMonsters.

Applies real-world environmental effects to a baseline torque curve before
the ECU optimizer runs.  Unity remains authoritative for final environment
effects; this module provides the Python-side baseline adjustment.

Effects modelled
----------------
Altitude
    Air density decreases with altitude following the barometric formula:
        ρ/ρ₀ = exp(−altitude_m / SCALE_HEIGHT_M)

    Naturally-aspirated (NA) engines lose power proportional to the full
    density drop.  Forced-induction engines partially compensate:
        - Turbo:        compensates 50 % of the density loss
        - Supercharged: compensates 30 % of the density loss

Temperature
    Hot air is less dense.  Each degree Celsius above the standard
    reference temperature (25 °C) reduces power by 0.1 %.
    Temperatures at or below standard incur no penalty.

Wear multiplier
    High ambient temperature accelerates part wear.  Each 10 °C above
    standard adds 5 % to the wear rate (returned as a multiplier ≥ 1.0).

All functions are pure and deterministic.  Non-finite inputs raise
``ValueError``.  Logs go to stderr only.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate atmospheric scale height (metres).
SCALE_HEIGHT_M: float = 8500.0

# Standard reference temperature (°C).
STD_TEMP_C: float = 25.0

# Power loss per °C above standard (fraction).
TEMP_POWER_LOSS_PER_DEG: float = 0.001  # 0.1 % per °C

# Wear rate increase per °C above standard (fraction).
TEMP_WEAR_GAIN_PER_DEG: float = 0.005  # 0.5 % per °C  → 5 % per 10 °C

# Fraction of altitude-induced density loss that each aspiration type
# compensates for.  0.0 = no compensation (full loss), 1.0 = full compensation.
_ALTITUDE_COMPENSATION: dict[str, float] = {
    "NA": 0.0,
    "Turbo": 0.5,
    "Supercharged": 0.3,
}

# Minimum power factor to prevent degenerate curves at extreme altitudes.
_MIN_POWER_FACTOR: float = 0.30


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _air_density_ratio(altitude_m: float) -> float:
    """Return air density relative to sea level using the barometric formula.

    Returns a value in (0, 1].  Sea level → 1.0.
    """
    return math.exp(-altitude_m / SCALE_HEIGHT_M)


def _altitude_power_factor(altitude_m: float, aspiration: str) -> float:
    """Return the power factor [_MIN_POWER_FACTOR, 1.0] due to altitude.

    Parameters
    ----------
    altitude_m:
        Altitude above sea level in metres (≥ 0).
    aspiration:
        ``"NA"``, ``"Turbo"``, or ``"Supercharged"``.
    """
    density_ratio = _air_density_ratio(altitude_m)
    compensation = _ALTITUDE_COMPENSATION.get(aspiration, 0.0)

    # Power loss = density deficit × (1 − compensation)
    power_loss = (1.0 - density_ratio) * (1.0 - compensation)
    factor = 1.0 - power_loss
    return max(_MIN_POWER_FACTOR, factor)


def _temperature_power_factor(ambient_temp_c: float) -> float:
    """Return the power factor [0.5, 1.0] due to ambient temperature.

    Temperatures at or below ``STD_TEMP_C`` return 1.0 (no penalty).
    """
    delta = max(0.0, ambient_temp_c - STD_TEMP_C)
    factor = 1.0 - delta * TEMP_POWER_LOSS_PER_DEG
    return max(0.5, factor)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_biome_modifier(
    torque_nm: list[float],
    altitude_m: float,
    ambient_temp_c: float,
    aspiration: str = "NA",
) -> list[float]:
    """Apply altitude and temperature modifiers to a torque curve.

    This function must be called *before* the ECU optimizer so that the
    optimizer searches within the biome-adjusted baseline.

    Parameters
    ----------
    torque_nm:
        Baseline torque array (Nm), one value per RPM bin.
    altitude_m:
        Altitude above sea level in metres.  Must be ≥ 0 and finite.
    ambient_temp_c:
        Ambient temperature in °C.  Must be finite.
    aspiration:
        Engine aspiration: ``"NA"``, ``"Turbo"``, or ``"Supercharged"``.
        Unknown values are treated as ``"NA"`` (most conservative).

    Returns
    -------
    list[float]
        Modified torque array, same length as *torque_nm*.

    Raises
    ------
    ValueError
        If *torque_nm* is empty, *altitude_m* is negative or non-finite,
        *ambient_temp_c* is non-finite, or any torque value is non-finite.
    """
    if not torque_nm:
        raise ValueError("torque_nm must not be empty")

    if not math.isfinite(altitude_m) or altitude_m < 0.0:
        raise ValueError(
            f"altitude_m must be a non-negative finite number, got {altitude_m!r}"
        )

    if not math.isfinite(ambient_temp_c):
        raise ValueError(
            f"ambient_temp_c must be finite, got {ambient_temp_c!r}"
        )

    for i, tq in enumerate(torque_nm):
        if not isinstance(tq, (int, float)) or not math.isfinite(tq):
            raise ValueError(f"Non-finite torque value at index {i}: {tq!r}")

    alt_factor = _altitude_power_factor(altitude_m, aspiration)
    temp_factor = _temperature_power_factor(ambient_temp_c)
    total_factor = alt_factor * temp_factor

    logger.debug(
        "Biome modifier: altitude=%.1f m, aspiration=%s, temp=%.1f °C | "
        "alt_factor=%.4f, temp_factor=%.4f, total=%.4f",
        altitude_m,
        aspiration,
        ambient_temp_c,
        alt_factor,
        temp_factor,
        total_factor,
    )

    return [round(tq * total_factor, 4) for tq in torque_nm]


def compute_wear_multiplier(ambient_temp_c: float) -> float:
    """Return a wear-rate multiplier based on ambient temperature.

    Higher temperatures accelerate part wear.  The multiplier is ≥ 1.0;
    temperatures at or below ``STD_TEMP_C`` return exactly 1.0.

    Parameters
    ----------
    ambient_temp_c:
        Ambient temperature in °C.  Must be finite.

    Returns
    -------
    float
        Wear multiplier ≥ 1.0.

    Raises
    ------
    ValueError
        If *ambient_temp_c* is non-finite.
    """
    if not math.isfinite(ambient_temp_c):
        raise ValueError(
            f"ambient_temp_c must be finite, got {ambient_temp_c!r}"
        )
    delta = max(0.0, ambient_temp_c - STD_TEMP_C)
    return round(1.0 + delta * TEMP_WEAR_GAIN_PER_DEG, 6)


def biome_summary(
    altitude_m: float,
    ambient_temp_c: float,
    aspiration: str = "NA",
) -> dict[str, float]:
    """Return a summary dict of all biome modifier factors.

    Useful for debugging and logging in Unity via the ECU contract.

    Parameters
    ----------
    altitude_m:
        Altitude above sea level in metres.
    ambient_temp_c:
        Ambient temperature in °C.
    aspiration:
        Engine aspiration type.

    Returns
    -------
    dict with keys:
        ``air_density_ratio``, ``altitude_power_factor``,
        ``temperature_power_factor``, ``total_power_factor``,
        ``wear_multiplier``
    """
    if not math.isfinite(altitude_m) or altitude_m < 0.0:
        raise ValueError(
            f"altitude_m must be a non-negative finite number, got {altitude_m!r}"
        )
    if not math.isfinite(ambient_temp_c):
        raise ValueError(
            f"ambient_temp_c must be finite, got {ambient_temp_c!r}"
        )

    density_ratio = _air_density_ratio(altitude_m)
    alt_factor = _altitude_power_factor(altitude_m, aspiration)
    temp_factor = _temperature_power_factor(ambient_temp_c)
    total_factor = alt_factor * temp_factor
    wear_mult = compute_wear_multiplier(ambient_temp_c)

    return {
        "air_density_ratio": round(density_ratio, 6),
        "altitude_power_factor": round(alt_factor, 6),
        "temperature_power_factor": round(temp_factor, 6),
        "total_power_factor": round(total_factor, 6),
        "wear_multiplier": wear_mult,
    }
