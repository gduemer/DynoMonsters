"""
ecu/optimizer.py

Bounded torque delta search for the ECU tuning assistant.

Strategy:
  - Uses a seeded random search (hill-climbing) within constraint bounds.
  - Each candidate is a Gaussian-shaped delta profile (smooth by construction).
  - Gaussian sigma is computed to guarantee the smoothness constraint is met.
  - Score = sum of proposed torque (higher is better), subject to all constraints.
  - Deterministic: identical seed + inputs → identical output.

Why Gaussian profiles?
  The smoothness constraint (max_second_derivative on the delta curve) requires
  that adjacent deltas change gradually. Independent per-bin random values easily
  violate this. A Gaussian bell-curve shape has a bounded second derivative:
      max |f''| ≈ peak / sigma^2
  By choosing sigma >= sqrt(peak / max_second_derivative), smoothness is
  guaranteed before validation even runs.
"""

import math
import random
import logging
from typing import Any

from ecu.validator import validate_proposal, ValidationError

logger = logging.getLogger(__name__)


def _compute_score(proposed_torque: list[float]) -> float:
    """Score = sum of proposed torque values. Higher is better."""
    return sum(proposed_torque)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _gaussian_delta_profile(
    rng: random.Random,
    baseline_torque_nm: list[float],
    constraints: dict[str, Any],
    scale: float = 1.0,
) -> list[float]:
    """
    Generate a smooth Gaussian-shaped delta profile within all constraint bounds.

    The Gaussian shape guarantees the smoothness constraint is satisfied:
        sigma >= sqrt(peak_amplitude / max_second_derivative)

    scale: exploration scale factor (0.0–1.0). Lower = more conservative peak.
    """
    n = len(baseline_torque_nm)

    max_bin_delta_nm: float = constraints.get("max_bin_delta_nm", 8.0)
    max_bin_delta_ratio: float = constraints.get("max_bin_delta_ratio", 0.03)
    smoothness_cfg: dict = constraints.get("smoothness", {})
    max_second_deriv: float = smoothness_cfg.get("max_second_derivative", 0.15)

    # Per-bin ceiling: tightest of absolute and ratio limits
    per_bin_limit = [
        min(max_bin_delta_nm, b * max_bin_delta_ratio)
        for b in baseline_torque_nm
    ]
    global_limit = min(per_bin_limit) * scale

    if global_limit <= 0.0 or max_second_deriv <= 0.0:
        return [0.0] * n

    # Peak amplitude: random within [0, global_limit]
    peak = rng.uniform(0.0, global_limit)

    if peak <= 0.0:
        return [0.0] * n

    # Sigma must satisfy: peak / sigma^2 <= max_second_deriv
    # => sigma >= sqrt(peak / max_second_deriv)
    min_sigma = math.sqrt(peak / max_second_deriv)

    # Upper bound: half the curve width (very wide = nearly flat = always smooth)
    max_sigma = max(float(n), min_sigma + 0.1)

    sigma = rng.uniform(min_sigma, max_sigma)

    # Center of the Gaussian (can be anywhere along the bins)
    center = rng.uniform(0.0, float(n - 1))

    # Generate Gaussian profile, clamped to per-bin limits
    deltas: list[float] = []
    for i in range(n):
        d = peak * math.exp(-0.5 * ((i - center) / sigma) ** 2)
        # Safety clamp: never exceed per-bin limit (handles edge cases)
        d = _clamp(d, 0.0, per_bin_limit[i])
        deltas.append(d)

    return deltas


def _pick_calibration(
    rng: random.Random,
    constraints: dict[str, Any],
) -> dict[str, float]:
    """
    Pick calibration values uniformly within allowed ranges.
    Falls back to a safe midpoint range if a parameter is not in constraints.
    """
    calibration_ranges: dict = constraints.get("calibration_ranges", {})

    defaults = {
        "afr_target": [12.5, 13.5],
        "ign_timing_deg": [0.0, 4.0],
        "boost_target_psi": [0.0, 14.0],
    }

    calibration: dict[str, float] = {}
    for param, fallback_range in defaults.items():
        if param in calibration_ranges:
            lo, hi = calibration_ranges[param]
        else:
            lo, hi = fallback_range
        # Ensure lo <= hi (defensive)
        if lo > hi:
            lo, hi = hi, lo
        calibration[param] = rng.uniform(lo, hi)

    return calibration


def run_optimization(
    baseline_torque_nm: list[float],
    rpm_bins: list[int],
    constraints: dict[str, Any],
    cycle_budget: int,
    seed: int,
) -> dict[str, Any]:
    """
    Run a seeded hill-climbing search for the best valid torque delta.

    Returns a dict with:
      - torque_delta_nm: list[float]
      - calibration: dict[str, float]
      - confidence: float (0.0–1.0)
      - estimated_peak_gain_ratio: float
      - cycles_used: int
      - best_score: float
      - warnings: list[str]
    """
    rng = random.Random(seed)

    n_bins = len(baseline_torque_nm)
    baseline_peak = max(baseline_torque_nm)

    # Start from zero delta (baseline is always valid)
    best_delta: list[float] = [0.0] * n_bins
    best_calibration = _pick_calibration(rng, constraints)
    best_score = _compute_score(baseline_torque_nm)
    best_warnings: list[str] = []
    cycles_used = 0

    for cycle in range(cycle_budget):
        cycles_used += 1
        # Exploration scale: start broad, tighten toward end (annealing-lite)
        scale = 1.0 - (cycle / max(cycle_budget, 1)) * 0.5  # 1.0 → 0.5

        candidate_delta = _gaussian_delta_profile(rng, baseline_torque_nm, constraints, scale)
        candidate_calibration = _pick_calibration(rng, constraints)

        try:
            warnings = validate_proposal(
                torque_delta_nm=candidate_delta,
                calibration=candidate_calibration,
                baseline_torque_nm=baseline_torque_nm,
                rpm_bins=rpm_bins,
                constraints=constraints,
            )
        except ValidationError as exc:
            logger.debug("Cycle %d: candidate rejected by validator: %s", cycle, exc)
            continue

        proposed = [b + d for b, d in zip(baseline_torque_nm, candidate_delta)]
        score = _compute_score(proposed)

        if score > best_score:
            best_delta = candidate_delta
            best_calibration = candidate_calibration
            best_score = score
            best_warnings = warnings
            logger.debug("Cycle %d: new best score=%.4f", cycle, best_score)

    # Compute final metrics
    proposed_peak = max(b + d for b, d in zip(baseline_torque_nm, best_delta))
    estimated_peak_gain_ratio = (
        (proposed_peak - baseline_peak) / baseline_peak
        if baseline_peak > 0
        else 0.0
    )

    # Confidence: how close are we to the gain cap?
    max_peak_gain_ratio: float = constraints.get("max_peak_gain_ratio", 0.02)
    confidence = _clamp(
        estimated_peak_gain_ratio / max_peak_gain_ratio
        if max_peak_gain_ratio > 0
        else 0.0,
        0.0,
        1.0,
    )

    logger.info(
        "Optimization complete: cycles=%d best_score=%.4f peak_gain=%.6f confidence=%.4f",
        cycles_used,
        best_score,
        estimated_peak_gain_ratio,
        confidence,
    )

    return {
        "torque_delta_nm": best_delta,
        "calibration": best_calibration,
        "confidence": round(confidence, 4),
        "estimated_peak_gain_ratio": round(estimated_peak_gain_ratio, 6),
        "cycles_used": cycles_used,
        "best_score": round(best_score, 4),
        "warnings": best_warnings,
    }
