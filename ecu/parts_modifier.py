"""Part upgrade effects on the baseline torque curve — DynoMonsters.

Physics basis
-------------
An intake upgrade reduces the pressure drop across the intake restriction.
By Bernoulli's principle, the pressure drop across a restriction is:

    ΔP = ½ρv²Cd

where v (air velocity) ∝ piston speed ∝ RPM.  Therefore:

    ΔP ∝ RPM²

The torque gain from reducing the restriction coefficient (ΔCd) is:

    ΔTorque_gain ∝ ΔCd × RPM²

Normalised to redline RPM, the gain ratio at any RPM bin is:

    gain_ratio(rpm) = BASE_GAIN × aspiration_scale × level_scale
                      × condition × (rpm / redline_rpm)²

This produces the characteristic dyno shape for an intake upgrade:
  - Near-zero gain at idle (low air velocity → negligible restriction loss)
  - Quadratic growth through the mid-range
  - Maximum gain at redline

Aspiration scaling
------------------
Forced-induction engines already overcome intake restriction via the
compressor/supercharger, so the intake upgrade benefits them less:
  - NA:           1.00 × (full benefit)
  - Turbo:        0.60 × (compressor compensates ~40 % of restriction)
  - Supercharged: 0.50 × (positive-displacement blower compensates ~50 %)

Level scaling (1–5)
-------------------
  Level 1 — stock replacement filter (baseline)
  Level 2 — high-flow panel filter (+25 %)
  Level 3 — short-ram intake, larger diameter (+55 %)
  Level 4 — cold-air intake, heat-shielded (+90 %)
  Level 5 — race intake, velocity stacks, no filter (+130 %)

Condition scaling
-----------------
A dirty or worn intake has reduced flow improvement.
  effective_gain = full_gain × condition   (condition ∈ [0.0, 1.0])

All functions are pure and deterministic.  Non-finite inputs raise ValueError.
Logs go to stderr only.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base fractional torque gain at redline for a Level-1 NA intake in new
# condition.  Derived from typical cold-air-intake dyno data:
# ~4 % peak gain on a naturally-aspirated engine.
INTAKE_BASE_GAIN: float = 0.04

# Level multipliers (index 0 unused; index 1–5 map to Level 1–5).
_LEVEL_SCALE: tuple[float, ...] = (
    0.0,   # unused
    1.00,  # Level 1 — stock replacement
    1.25,  # Level 2 — high-flow filter
    1.55,  # Level 3 — short-ram intake
    1.90,  # Level 4 — cold-air intake
    2.30,  # Level 5 — race intake / velocity stacks
)

# Aspiration scaling factors.
_ASPIRATION_SCALE: dict[str, float] = {
    "NA": 1.00,
    "Turbo": 0.60,
    "Supercharged": 0.50,
}

# Supported part categories and their handler keys.
SUPPORTED_CATEGORIES: frozenset[str] = frozenset({"intake"})


# ---------------------------------------------------------------------------
# Part profile dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PartProfile:
    """Describes how a part category modifies the torque curve.

    Attributes
    ----------
    category:
        Part category string (e.g. ``"intake"``).
    base_gain:
        Maximum fractional torque gain at redline for Level-1, NA,
        new-condition (condition=1.0).
    level_scale:
        Tuple of multipliers indexed by level (1–5).
    aspiration_scale:
        Dict mapping aspiration type to a scaling factor.
    description:
        Human-readable description of the part effect.
    """

    category: str
    base_gain: float
    level_scale: tuple[float, ...]
    aspiration_scale: dict[str, float]
    description: str = ""

    def gain_at_rpm(
        self,
        rpm: int,
        redline_rpm: int,
        aspiration: str,
        level: int,
        condition: float,
    ) -> float:
        """Return the fractional torque gain at a single RPM bin.

        Parameters
        ----------
        rpm:
            Current RPM bin.
        redline_rpm:
            Engine redline RPM.
        aspiration:
            ``"NA"``, ``"Turbo"``, or ``"Supercharged"``.
        level:
            Part level (1–5).
        condition:
            Part condition in [0.0, 1.0].

        Returns
        -------
        float
            Fractional gain to apply to the torque value at this bin.
            Always ≥ 0.
        """
        if redline_rpm <= 0:
            return 0.0

        # Normalised RPM position [0, 1]
        rpm_norm = rpm / redline_rpm

        # Quadratic pressure-drop physics: gain ∝ RPM²
        rpm_factor = rpm_norm ** 2

        # Level scaling (clamp to valid range)
        lvl = max(1, min(5, level))
        lvl_scale = self.level_scale[lvl]

        # Aspiration scaling (unknown aspiration → most conservative = NA)
        asp_scale = self.aspiration_scale.get(aspiration, 1.0)

        return self.base_gain * lvl_scale * asp_scale * condition * rpm_factor


# ---------------------------------------------------------------------------
# Built-in part profiles
# ---------------------------------------------------------------------------

INTAKE_PROFILE = PartProfile(
    category="intake",
    base_gain=INTAKE_BASE_GAIN,
    level_scale=_LEVEL_SCALE,
    aspiration_scale=_ASPIRATION_SCALE,
    description=(
        "Intake upgrade: reduces intake restriction pressure drop (ΔP ∝ RPM²). "
        "Gain is near-zero at idle and grows quadratically to peak at redline."
    ),
)

#: Registry of all built-in part profiles, keyed by category.
PART_PROFILES: dict[str, PartProfile] = {
    "intake": INTAKE_PROFILE,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_part_effects(
    torque_nm: list[float],
    rpm_bins: list[int],
    redline_rpm: int,
    parts: list[dict[str, Any]],
    aspiration: str = "NA",
) -> list[float]:
    """Apply all equipped part upgrades to a baseline torque curve.

    This function must be called *after* biome modifiers and *before* the
    ECU optimizer, so the optimizer searches within the part-adjusted baseline.

    Each part dict must contain at minimum:
        ``{"category": str, "level": int, "condition": float}``

    Parts whose category is not in ``SUPPORTED_CATEGORIES`` are silently
    skipped (logged at DEBUG level).

    Parameters
    ----------
    torque_nm:
        Baseline torque array (Nm), one value per RPM bin.
    rpm_bins:
        RPM bin array, same length as *torque_nm*.
    redline_rpm:
        Engine redline RPM.  Used to normalise RPM position.
    parts:
        List of equipped part dicts.
    aspiration:
        Engine aspiration: ``"NA"``, ``"Turbo"``, or ``"Supercharged"``.

    Returns
    -------
    list[float]
        Modified torque array, same length as *torque_nm*.

    Raises
    ------
    ValueError
        If arrays are empty, mismatched, *redline_rpm* ≤ 0, or any torque
        value is non-finite.
    """
    if not torque_nm:
        raise ValueError("torque_nm must not be empty")
    if len(torque_nm) != len(rpm_bins):
        raise ValueError(
            f"Array length mismatch: torque_nm={len(torque_nm)}, "
            f"rpm_bins={len(rpm_bins)}"
        )
    if redline_rpm <= 0:
        raise ValueError(f"redline_rpm must be positive, got {redline_rpm}")

    for i, tq in enumerate(torque_nm):
        if not isinstance(tq, (int, float)) or not math.isfinite(tq):
            raise ValueError(f"Non-finite torque value at index {i}: {tq!r}")

    # Accumulate additive gain ratios per bin from all equipped parts.
    # Multiple parts of the same category stack additively (diminishing
    # returns are a Unity-side gameplay concern, not modelled here).
    gain_ratios = [0.0] * len(torque_nm)

    for part in parts:
        category = str(part.get("category", "")).lower()
        if category not in SUPPORTED_CATEGORIES:
            logger.debug("Skipping unsupported part category: %r", category)
            continue

        profile = PART_PROFILES[category]
        level = int(part.get("level", 1))
        condition = float(part.get("condition", 1.0))

        # Validate condition
        if not math.isfinite(condition):
            logger.warning(
                "Part %r has non-finite condition %r, skipping",
                part.get("part_id", "?"),
                condition,
            )
            continue
        condition = max(0.0, min(1.0, condition))

        for i, rpm in enumerate(rpm_bins):
            gain_ratios[i] += profile.gain_at_rpm(
                rpm=rpm,
                redline_rpm=redline_rpm,
                aspiration=aspiration,
                level=level,
                condition=condition,
            )

    # Apply accumulated gains to the torque curve.
    result: list[float] = []
    for tq, gain_ratio in zip(torque_nm, gain_ratios):
        new_tq = tq * (1.0 + gain_ratio)
        if not math.isfinite(new_tq):
            raise ValueError(
                f"Non-finite result after applying part gains: "
                f"tq={tq}, gain_ratio={gain_ratio}"
            )
        result.append(round(new_tq, 4))

    # Log summary
    if parts:
        peak_gain_pct = max(gain_ratios) * 100.0
        logger.debug(
            "Parts modifier: %d part(s) applied, aspiration=%s, "
            "peak_gain=%.2f%%",
            len(parts),
            aspiration,
            peak_gain_pct,
        )

    return result


def intake_gain_curve(
    rpm_bins: list[int],
    redline_rpm: int,
    aspiration: str = "NA",
    level: int = 1,
    condition: float = 1.0,
) -> list[float]:
    """Return the fractional gain at each RPM bin for an intake upgrade.

    Convenience function for visualisation and debugging.

    Parameters
    ----------
    rpm_bins:
        RPM bin array.
    redline_rpm:
        Engine redline RPM.
    aspiration:
        Engine aspiration type.
    level:
        Intake level (1–5).
    condition:
        Intake condition [0.0, 1.0].

    Returns
    -------
    list[float]
        Fractional gain values (e.g. 0.04 = 4 % torque gain) at each bin.
    """
    profile = PART_PROFILES["intake"]
    return [
        profile.gain_at_rpm(
            rpm=rpm,
            redline_rpm=redline_rpm,
            aspiration=aspiration,
            level=level,
            condition=condition,
        )
        for rpm in rpm_bins
    ]
