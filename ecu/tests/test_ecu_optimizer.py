"""Tests for ecu.ecu_optimizer — deterministic ECU tuning stub."""

import math

from ecu.ecu_optimizer import optimize

# A small but realistic baseline curve for testing.
_RPM_BINS = [1000, 2000, 3000, 4000, 5000, 6000, 7000]
_BASELINE_TQ = [120.0, 180.0, 220.0, 240.0, 235.0, 210.0, 170.0]
_CONSTRAINTS = {
    "max_peak_gain_ratio": 0.02,
    "max_bin_delta_nm": 8.0,
    "max_bin_delta_ratio": 0.03,
    "max_total_variation_ratio": 0.02,
    "smoothness": {"max_second_derivative": 0.15},
    "calibration_ranges": {
        "afr_target": [11.5, 14.7],
        "ign_timing_deg": [-2.0, 8.0],
        "boost_target_psi": [0.0, 22.0],
    },
}


class TestOptimize:
    def test_deterministic_same_seed(self):
        """Same inputs + same seed → identical outputs."""
        r1 = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 40, seed=42)
        r2 = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 40, seed=42)
        assert r1["torque_delta_nm"] == r2["torque_delta_nm"]
        assert r1["calibration"] == r2["calibration"]
        assert r1["confidence"] == r2["confidence"]

    def test_different_seed_differs(self):
        """Different seeds should (very likely) produce different output."""
        r1 = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 40, seed=1)
        r2 = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 40, seed=999)
        # At least one delta should differ
        assert r1["torque_delta_nm"] != r2["torque_delta_nm"]

    def test_peak_gain_within_cap(self):
        """Peak torque gain must not exceed max_peak_gain_ratio."""
        result = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 100, seed=7)
        deltas = result["torque_delta_nm"]
        baseline_peak = max(_BASELINE_TQ)
        proposed = [t + d for t, d in zip(_BASELINE_TQ, deltas)]
        proposed_peak = max(proposed)
        gain = (proposed_peak - baseline_peak) / baseline_peak
        assert gain <= _CONSTRAINTS["max_peak_gain_ratio"] + 1e-9

    def test_bin_deltas_within_cap(self):
        """Each bin delta must respect max_bin_delta_nm."""
        result = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 100, seed=7)
        for d in result["torque_delta_nm"]:
            assert abs(d) <= _CONSTRAINTS["max_bin_delta_nm"] + 1e-9

    def test_calibration_within_ranges(self):
        """Calibration values must fall within allowed ranges."""
        result = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 40, seed=42)
        cal = result["calibration"]
        ranges = _CONSTRAINTS["calibration_ranges"]
        assert ranges["afr_target"][0] <= cal["afr_target"] <= ranges["afr_target"][1]
        assert (
            ranges["ign_timing_deg"][0]
            <= cal["ign_timing_deg"]
            <= ranges["ign_timing_deg"][1]
        )
        assert (
            ranges["boost_target_psi"][0]
            <= cal["boost_target_psi"]
            <= ranges["boost_target_psi"][1]
        )

    def test_no_nan_or_inf_in_deltas(self):
        """Deltas must never contain NaN or Inf."""
        result = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 40, seed=42)
        for d in result["torque_delta_nm"]:
            assert math.isfinite(d)

    def test_returns_expected_keys(self):
        result = optimize(_RPM_BINS, _BASELINE_TQ, _CONSTRAINTS, 10, seed=1)
        expected = {
            "torque_delta_nm",
            "calibration",
            "confidence",
            "estimated_peak_gain_ratio",
            "cycles_used",
            "best_score",
            "notes",
            "warnings",
        }
        assert set(result.keys()) == expected
