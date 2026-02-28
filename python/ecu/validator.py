"""
ecu/validator.py

Validates an ECU proposal against the constraints provided by Unity.
Unity is authoritative — this mirrors the same rules Unity enforces,
so Python can self-reject before returning a bad proposal.

Rules enforced (must match ECU_CONTRACT.md §5):
  - torque_delta length matches rpm_bins length
  - no NaN or infinity in torque_delta
  - abs(delta) <= max_bin_delta_nm for every bin
  - abs(delta) / baseline_torque <= max_bin_delta_ratio for every bin
  - applying delta does not yield peak gain above max_peak_gain_ratio
  - second derivative of proposed curve <= max_second_derivative (smoothness)
  - calibration values within calibration_ranges
"""

import math
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when a proposal violates a constraint."""
    pass


def _is_finite(value: float) -> bool:
    return math.isfinite(value)


def validate_proposal(
    torque_delta_nm: list[float],
    calibration: dict[str, float],
    baseline_torque_nm: list[float],
    rpm_bins: list[int],
    constraints: dict[str, Any],
) -> list[str]:
    """
    Validate a proposed torque delta and calibration against constraints.

    Returns a list of warning strings (empty = fully valid).
    Raises ValidationError on hard violations.

    Parameters
    ----------
    torque_delta_nm      : proposed per-bin torque deltas
    calibration          : proposed calibration dict (afr_target, ign_timing_deg, etc.)
    baseline_torque_nm   : baseline torque values from Unity
    rpm_bins             : RPM bin array from Unity
    constraints          : constraints dict from the request JSON
    """
    warnings: list[str] = []

    # ── 1. Length match ──────────────────────────────────────────────────────
    if len(torque_delta_nm) != len(rpm_bins):
        raise ValidationError(
            f"torque_delta length {len(torque_delta_nm)} != rpm_bins length {len(rpm_bins)}"
        )
    if len(baseline_torque_nm) != len(rpm_bins):
        raise ValidationError(
            f"baseline_torque length {len(baseline_torque_nm)} != rpm_bins length {len(rpm_bins)}"
        )

    max_bin_delta_nm: float = constraints.get("max_bin_delta_nm", 8.0)
    max_bin_delta_ratio: float = constraints.get("max_bin_delta_ratio", 0.03)
    max_peak_gain_ratio: float = constraints.get("max_peak_gain_ratio", 0.02)
    smoothness_cfg: dict = constraints.get("smoothness", {})
    max_second_derivative: float = smoothness_cfg.get("max_second_derivative", 0.15)
    calibration_ranges: dict = constraints.get("calibration_ranges", {})

    # ── 2. NaN / infinity check ───────────────────────────────────────────────
    for i, delta in enumerate(torque_delta_nm):
        if not _is_finite(delta):
            raise ValidationError(f"torque_delta[{i}] is not finite: {delta}")

    # ── 3. Per-bin delta limits ───────────────────────────────────────────────
    for i, (delta, baseline) in enumerate(zip(torque_delta_nm, baseline_torque_nm)):
        if not _is_finite(baseline) or baseline <= 0:
            raise ValidationError(
                f"baseline_torque_nm[{i}] is invalid: {baseline}"
            )
        abs_delta = abs(delta)
        if abs_delta > max_bin_delta_nm:
            raise ValidationError(
                f"bin {i} delta {delta:.4f} Nm exceeds max_bin_delta_nm {max_bin_delta_nm}"
            )
        ratio = abs_delta / baseline
        if ratio > max_bin_delta_ratio:
            raise ValidationError(
                f"bin {i} delta ratio {ratio:.4f} exceeds max_bin_delta_ratio {max_bin_delta_ratio}"
            )

    # ── 4. Peak gain cap ─────────────────────────────────────────────────────
    baseline_peak = max(baseline_torque_nm)
    proposed = [b + d for b, d in zip(baseline_torque_nm, torque_delta_nm)]
    proposed_peak = max(proposed)

    if baseline_peak > 0:
        peak_gain_ratio = (proposed_peak - baseline_peak) / baseline_peak
        if peak_gain_ratio > max_peak_gain_ratio:
            raise ValidationError(
                f"peak gain ratio {peak_gain_ratio:.4f} exceeds cap {max_peak_gain_ratio}"
            )
        if peak_gain_ratio < 0:
            warnings.append(
                f"proposal reduces peak torque by {abs(peak_gain_ratio)*100:.2f}%"
            )

    # ── 5. Smoothness — second derivative check on the delta curve ────────────
    # The baseline curve is Unity's and is already valid.
    # Python only controls the deltas, so smoothness is enforced on torque_delta_nm.
    # max_second_derivative is an absolute Nm threshold on the delta curve.
    if len(torque_delta_nm) >= 3:
        for i in range(1, len(torque_delta_nm) - 1):
            second_deriv = abs(
                torque_delta_nm[i + 1]
                - 2 * torque_delta_nm[i]
                + torque_delta_nm[i - 1]
            )
            if second_deriv > max_second_derivative:
                raise ValidationError(
                    f"smoothness violation at bin {i}: "
                    f"delta second_derivative={second_deriv:.4f} "
                    f"> max {max_second_derivative}"
                )

    # ── 6. Calibration ranges ─────────────────────────────────────────────────
    for param, value in calibration.items():
        if not _is_finite(value):
            raise ValidationError(f"calibration.{param} is not finite: {value}")
        if param in calibration_ranges:
            lo, hi = calibration_ranges[param]
            if not (lo <= value <= hi):
                raise ValidationError(
                    f"calibration.{param}={value} outside allowed range [{lo}, {hi}]"
                )

    logger.debug("Proposal passed all validation checks. Warnings: %s", warnings)
    return warnings
