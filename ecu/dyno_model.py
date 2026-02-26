"""Core dyno math for DynoMonsters.

HP = (torque_nm * RPM) / 5252

All curves are represented as parallel arrays of rpm_bins (int) and
torque_nm (float).  HP is always derived, never stored as source-of-truth.
"""

from __future__ import annotations

import math
from typing import NamedTuple


HP_CONSTANT = 5252


class CurvePeaks(NamedTuple):
    """Peak values extracted from a dyno curve."""

    peak_torque_nm: float
    peak_torque_rpm: int
    peak_hp: float
    peak_hp_rpm: int


def compute_hp(torque_nm: float, rpm: int) -> float:
    """Return horsepower for a single RPM/torque point.

    Raises ``ValueError`` on non-finite inputs.
    """
    if not math.isfinite(torque_nm) or not math.isfinite(rpm):
        raise ValueError(f"Non-finite input: torque_nm={torque_nm}, rpm={rpm}")
    if rpm == 0:
        return 0.0
    return (torque_nm * rpm) / HP_CONSTANT


def compute_hp_curve(
    rpm_bins: list[int],
    torque_nm: list[float],
) -> list[float]:
    """Derive an HP array from parallel RPM/torque arrays.

    Raises ``ValueError`` when the arrays are mismatched or contain
    non-finite values.
    """
    if len(rpm_bins) != len(torque_nm):
        raise ValueError(
            f"Array length mismatch: rpm_bins={len(rpm_bins)}, "
            f"torque_nm={len(torque_nm)}"
        )
    return [compute_hp(tq, rpm) for tq, rpm in zip(torque_nm, rpm_bins)]


def find_peaks(
    rpm_bins: list[int],
    torque_nm: list[float],
) -> CurvePeaks:
    """Return peak torque and peak HP with their RPM locations.

    Raises ``ValueError`` on empty or mismatched arrays.
    """
    if not rpm_bins:
        raise ValueError("Empty curve")
    hp_curve = compute_hp_curve(rpm_bins, torque_nm)

    max_tq_idx = 0
    max_hp_idx = 0
    for i in range(len(rpm_bins)):
        if torque_nm[i] > torque_nm[max_tq_idx]:
            max_tq_idx = i
        if hp_curve[i] > hp_curve[max_hp_idx]:
            max_hp_idx = i

    return CurvePeaks(
        peak_torque_nm=torque_nm[max_tq_idx],
        peak_torque_rpm=rpm_bins[max_tq_idx],
        peak_hp=hp_curve[max_hp_idx],
        peak_hp_rpm=rpm_bins[max_hp_idx],
    )


def apply_torque_deltas(
    torque_nm: list[float],
    deltas: list[float],
) -> list[float]:
    """Return a new torque array with deltas applied.

    Raises ``ValueError`` on length mismatch or non-finite values.
    """
    if len(torque_nm) != len(deltas):
        raise ValueError(
            f"Array length mismatch: torque_nm={len(torque_nm)}, "
            f"deltas={len(deltas)}"
        )
    result: list[float] = []
    for tq, d in zip(torque_nm, deltas):
        val = tq + d
        if not math.isfinite(val):
            raise ValueError(f"Non-finite result: {tq} + {d} = {val}")
        result.append(val)
    return result
