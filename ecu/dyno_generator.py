"""Dyno curve generator for DynoMonsters.

Produces a 500-point HP/TQ curve from a Car specification.

The torque shape is modelled as a Gaussian bell curve:
  - Rises from idle RPM
  - Peaks at approximately 65 % of the RPM range
  - Falls toward redline

HP is always derived from torque using the canonical formula:
    HP = (Torque_Nm * RPM) / 5252

All output values are finite; non-finite inputs raise ValueError.
"""

from __future__ import annotations

import math
import logging
from typing import NamedTuple

from ecu.car import Car
from ecu.dyno_model import compute_hp_curve

logger = logging.getLogger(__name__)

# Number of data points in every generated curve.
CURVE_POINTS: int = 500

# Gaussian shape parameters (normalised RPM position 0 → 1).
_PEAK_POSITION: float = 0.65   # torque peak at 65 % of RPM range
_SIGMA: float = 0.30            # width of the bell curve
_MIN_TORQUE_FACTOR: float = 0.55  # idle torque as fraction of peak torque


class DynoCurve(NamedTuple):
    """A fully computed 500-point dyno curve."""

    rpm_bins: list[int]
    torque_nm: list[float]
    hp: list[float]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _torque_at_rpm(
    base_torque_nm: float,
    rpm: int,
    idle_rpm: int,
    redline_rpm: int,
) -> float:
    """Return modelled torque (Nm) at a single RPM point.

    Uses a Gaussian bell curve so the shape feels like a real engine:
    - Minimum torque at idle = ``_MIN_TORQUE_FACTOR * base_torque_nm``
    - Peak torque at ``_PEAK_POSITION`` of the RPM range
    """
    rpm_range = redline_rpm - idle_rpm
    if rpm_range <= 0:
        return base_torque_nm

    # Normalised position in [0, 1]
    t = (rpm - idle_rpm) / rpm_range

    # Gaussian envelope
    gaussian = math.exp(-((t - _PEAK_POSITION) ** 2) / (2.0 * _SIGMA ** 2))

    torque = base_torque_nm * (_MIN_TORQUE_FACTOR + (1.0 - _MIN_TORQUE_FACTOR) * gaussian)
    return round(torque, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_dyno_curve(car: Car, idle_rpm: int = 800) -> DynoCurve:
    """Generate a ``CURVE_POINTS``-point HP/TQ curve for *car*.

    Parameters
    ----------
    car:
        A validated ``Car`` instance.
    idle_rpm:
        Starting RPM for the curve (default 800).  Must be less than
        ``car.redline_rpm``.

    Returns
    -------
    DynoCurve
        Named tuple with ``rpm_bins``, ``torque_nm``, and ``hp`` arrays,
        each of length ``CURVE_POINTS``.

    Raises
    ------
    ValueError
        If the Car fails validation or ``idle_rpm >= car.redline_rpm``.
    """
    errors = car.validate()
    if errors:
        raise ValueError(f"Invalid Car: {errors}")

    if idle_rpm <= 0:
        raise ValueError(f"idle_rpm must be positive, got {idle_rpm}")

    if idle_rpm >= car.redline_rpm:
        raise ValueError(
            f"idle_rpm ({idle_rpm}) must be less than redline_rpm ({car.redline_rpm})"
        )

    # Build 500 evenly-spaced RPM bins from idle to redline (inclusive).
    step = (car.redline_rpm - idle_rpm) / (CURVE_POINTS - 1)
    rpm_bins: list[int] = [
        int(round(idle_rpm + i * step)) for i in range(CURVE_POINTS)
    ]

    # Ensure the last bin is exactly redline (avoids float rounding drift).
    rpm_bins[-1] = car.redline_rpm

    # Compute torque at each bin.
    torque_nm: list[float] = [
        _torque_at_rpm(car.base_torque_nm, rpm, idle_rpm, car.redline_rpm)
        for rpm in rpm_bins
    ]

    # Derive HP from torque (reuses validated dyno_model logic).
    hp_raw = compute_hp_curve(rpm_bins, torque_nm)
    hp: list[float] = [round(h, 4) for h in hp_raw]

    logger.debug(
        "Generated dyno curve for %s %s %d: %d points, "
        "peak_tq=%.1f Nm, peak_hp=%.1f HP",
        car.make,
        car.model,
        car.year,
        CURVE_POINTS,
        max(torque_nm),
        max(hp),
    )

    return DynoCurve(rpm_bins=rpm_bins, torque_nm=torque_nm, hp=hp)
