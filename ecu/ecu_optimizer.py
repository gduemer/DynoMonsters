"""Deterministic ECU optimizer stub — Phase 0.

Searches within allowed calibration bounds to produce a small torque-curve
improvement.  All randomness is seeded so that identical inputs + seed yield
identical outputs.
"""

from __future__ import annotations

import logging
import math
import random

from ecu.dyno_model import apply_torque_deltas, find_peaks

logger = logging.getLogger(__name__)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _second_derivative_ok(
    torque: list[float],
    max_second_deriv: float,
) -> bool:
    """Check smoothness via approximate second derivative."""
    for i in range(1, len(torque) - 1):
        d2 = abs(torque[i - 1] - 2 * torque[i] + torque[i + 1])
        if d2 > max_second_deriv * torque[i]:
            return False
    return True


def optimize(
    rpm_bins: list[int],
    baseline_torque: list[float],
    constraints: dict,
    cycle_budget: int,
    seed: int,
    parts: list[dict] | None = None,
) -> dict:
    """Run the deterministic ECU tuning stub.

    Returns a dict with keys:
        torque_delta_nm, calibration, confidence,
        estimated_peak_gain_ratio, cycles_used, best_score, notes, warnings
    """
    rng = random.Random(seed)
    n = len(rpm_bins)

    max_peak_gain = constraints.get("max_peak_gain_ratio", 0.02)
    max_bin_delta = constraints.get("max_bin_delta_nm", 8.0)
    max_bin_ratio = constraints.get("max_bin_delta_ratio", 0.03)
    smoothness_cfg = constraints.get("smoothness", {})
    max_second_deriv = smoothness_cfg.get("max_second_derivative", 0.15)

    cal_ranges = constraints.get("calibration_ranges", {})
    afr_range = cal_ranges.get("afr_target", [11.5, 14.7])
    ign_range = cal_ranges.get("ign_timing_deg", [-2.0, 8.0])
    boost_range = cal_ranges.get("boost_target_psi", [0.0, 22.0])

    baseline_peaks = find_peaks(rpm_bins, baseline_torque)
    baseline_peak_tq = baseline_peaks.peak_torque_nm

    best_deltas = [0.0] * n
    best_score: float = 0.0
    best_calibration = {
        "afr_target": (afr_range[0] + afr_range[1]) / 2,
        "ign_timing_deg": (ign_range[0] + ign_range[1]) / 2,
        "boost_target_psi": (boost_range[0] + boost_range[1]) / 2,
    }

    notes: list[str] = []
    warnings: list[str] = []

    for cycle in range(cycle_budget):
        candidate = [0.0] * n
        for i in range(n):
            per_bin_cap = min(
                max_bin_delta,
                baseline_torque[i] * max_bin_ratio,
            )
            candidate[i] = rng.uniform(-per_bin_cap * 0.1, per_bin_cap)

        # Apply and check peak gain
        proposed = apply_torque_deltas(baseline_torque, candidate)
        proposed_peaks = find_peaks(rpm_bins, proposed)
        gain_ratio = (
            (proposed_peaks.peak_torque_nm - baseline_peak_tq)
            / baseline_peak_tq
            if baseline_peak_tq > 0
            else 0.0
        )

        if gain_ratio > max_peak_gain:
            # Scale deltas down to stay within cap
            if gain_ratio > 0:
                scale = max_peak_gain / gain_ratio * 0.95
                candidate = [d * scale for d in candidate]
                proposed = apply_torque_deltas(baseline_torque, candidate)
                proposed_peaks = find_peaks(rpm_bins, proposed)
                gain_ratio = (
                    (proposed_peaks.peak_torque_nm - baseline_peak_tq)
                    / baseline_peak_tq
                    if baseline_peak_tq > 0
                    else 0.0
                )

        # Smoothness check
        if not _second_derivative_ok(proposed, max_second_deriv):
            continue

        # Score: higher torque sum is better (simple heuristic)
        score = sum(candidate)
        if score > best_score:
            best_score = score
            best_deltas = candidate

    # Final calibration: pick values within ranges (deterministic from seed)
    best_calibration = {
        "afr_target": round(
            _clamp(rng.uniform(afr_range[0], afr_range[1]), *afr_range), 2
        ),
        "ign_timing_deg": round(
            _clamp(rng.uniform(ign_range[0], ign_range[1]), *ign_range), 2
        ),
        "boost_target_psi": round(
            _clamp(rng.uniform(boost_range[0], boost_range[1]), *boost_range),
            2,
        ),
    }

    # Final peak-gain ratio
    final_proposed = apply_torque_deltas(baseline_torque, best_deltas)
    final_peaks = find_peaks(rpm_bins, final_proposed)
    estimated_peak_gain = (
        (final_peaks.peak_torque_nm - baseline_peak_tq) / baseline_peak_tq
        if baseline_peak_tq > 0
        else 0.0
    )

    # Confidence: fraction of cycle budget that produced improvements
    confidence = _clamp(best_score / max(sum(baseline_torque), 1.0), 0.0, 1.0)

    # Validate no NaN/Inf leaked through
    for i, d in enumerate(best_deltas):
        if not math.isfinite(d):
            warnings.append(f"Non-finite delta at bin {i}, zeroed out")
            best_deltas[i] = 0.0

    return {
        "torque_delta_nm": [round(d, 4) for d in best_deltas],
        "calibration": best_calibration,
        "confidence": round(confidence, 4),
        "estimated_peak_gain_ratio": round(estimated_peak_gain, 6),
        "cycles_used": cycle_budget,
        "best_score": round(best_score, 4),
        "notes": notes,
        "warnings": warnings,
    }
