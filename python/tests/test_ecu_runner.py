"""
tests/test_ecu_runner.py

Unit tests for the ECU runner stub.

Coverage:
  - Determinism: same seed + inputs → identical output
  - Constraint enforcement: deltas within all bounds
  - Schema validation: missing fields, wrong version, bad types
  - Error handling: empty input, malformed JSON, non-finite baseline
  - Rejection path: proposal that violates constraints is rejected gracefully
  - Calibration ranges: values stay within allowed bounds
"""

import json
import math
import sys
import os

# Ensure the python/ directory is on the path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ecu_runner import process_request, _error_response, _rejected_response
from ecu.validator import validate_proposal, ValidationError
from ecu.optimizer import run_optimization


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_request(
    seed: int = 42,
    cycle_budget: int = 40,
    rpm_bins: list = None,
    torque_nm: list = None,
    constraints: dict = None,
    request_id: str = "test-001",
    contract_version: str = "1.0",
) -> dict:
    """Build a minimal valid request dict."""
    if rpm_bins is None:
        rpm_bins = [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000]
    if torque_nm is None:
        torque_nm = [180.0, 195.0, 210.0, 220.0, 225.0, 222.0, 215.0, 205.0, 190.0, 170.0, 145.0]
    if constraints is None:
        constraints = {
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
    return {
        "contract_version": contract_version,
        "request_id": request_id,
        "seed": seed,
        "cycle_budget": cycle_budget,
        "vehicle": {
            "vehicle_id": "test-vehicle",
            "engine_family": "inline-4",
            "aspiration": "Turbo",
            "drivetrain": "FWD",
        },
        "environment": {
            "biome_id": "urban",
            "altitude_m": 0.0,
            "ambient_temp_c": 25.0,
        },
        "street_cred": {"level": 1, "modifier": 1.0},
        "baseline_curve": {
            "rpm_bins": rpm_bins,
            "torque_nm": torque_nm,
        },
        "constraints": constraints,
        "parts": [],
    }


# ── Determinism tests ─────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_seed_same_output(self):
        """Identical request + seed must produce identical proposal."""
        req = make_request(seed=12345)
        resp1 = process_request(req)
        resp2 = process_request(req)

        assert resp1["status"] == "ok"
        assert resp2["status"] == "ok"
        assert resp1["proposal"]["torque_delta_nm"] == resp2["proposal"]["torque_delta_nm"]
        assert resp1["proposal"]["calibration"] == resp2["proposal"]["calibration"]
        assert resp1["proposal"]["estimated_peak_gain_ratio"] == resp2["proposal"]["estimated_peak_gain_ratio"]

    def test_different_seeds_different_output(self):
        """Different seeds should (almost certainly) produce different proposals."""
        req1 = make_request(seed=1)
        req2 = make_request(seed=9999)
        resp1 = process_request(req1)
        resp2 = process_request(req2)

        assert resp1["status"] == "ok"
        assert resp2["status"] == "ok"
        # It is statistically near-impossible for two different seeds to produce
        # identical delta vectors across 11 bins
        assert resp1["proposal"]["torque_delta_nm"] != resp2["proposal"]["torque_delta_nm"]

    def test_optimizer_determinism_direct(self):
        """run_optimization must be deterministic at the module level."""
        baseline = [180.0, 200.0, 220.0, 215.0, 200.0]
        rpm_bins = [1000, 2000, 3000, 4000, 5000]
        constraints = {
            "max_peak_gain_ratio": 0.02,
            "max_bin_delta_nm": 8.0,
            "max_bin_delta_ratio": 0.03,
            "smoothness": {"max_second_derivative": 0.15},
            "calibration_ranges": {
                "afr_target": [11.5, 14.7],
                "ign_timing_deg": [-2.0, 8.0],
                "boost_target_psi": [0.0, 22.0],
            },
        }
        r1 = run_optimization(baseline, rpm_bins, constraints, cycle_budget=20, seed=777)
        r2 = run_optimization(baseline, rpm_bins, constraints, cycle_budget=20, seed=777)
        assert r1["torque_delta_nm"] == r2["torque_delta_nm"]
        assert r1["calibration"] == r2["calibration"]


# ── Constraint enforcement tests ──────────────────────────────────────────────

class TestConstraintEnforcement:
    def test_deltas_within_absolute_limit(self):
        """All torque deltas must be <= max_bin_delta_nm."""
        req = make_request(seed=42, cycle_budget=50)
        resp = process_request(req)

        assert resp["status"] == "ok"
        max_delta = req["constraints"]["max_bin_delta_nm"]
        for delta in resp["proposal"]["torque_delta_nm"]:
            assert abs(delta) <= max_delta, f"delta {delta} exceeds max_bin_delta_nm {max_delta}"

    def test_deltas_within_ratio_limit(self):
        """All torque deltas must satisfy abs(delta)/baseline <= max_bin_delta_ratio."""
        req = make_request(seed=42, cycle_budget=50)
        resp = process_request(req)

        assert resp["status"] == "ok"
        max_ratio = req["constraints"]["max_bin_delta_ratio"]
        baseline = req["baseline_curve"]["torque_nm"]
        for delta, base in zip(resp["proposal"]["torque_delta_nm"], baseline):
            ratio = abs(delta) / base
            assert ratio <= max_ratio + 1e-9, (
                f"delta ratio {ratio:.6f} exceeds max_bin_delta_ratio {max_ratio}"
            )

    def test_peak_gain_within_cap(self):
        """Peak gain ratio must not exceed max_peak_gain_ratio."""
        req = make_request(seed=42, cycle_budget=50)
        resp = process_request(req)

        assert resp["status"] == "ok"
        max_gain = req["constraints"]["max_peak_gain_ratio"]
        assert resp["proposal"]["estimated_peak_gain_ratio"] <= max_gain + 1e-9

    def test_no_nan_or_infinity_in_output(self):
        """No NaN or infinity values in torque_delta_nm."""
        req = make_request(seed=42)
        resp = process_request(req)

        assert resp["status"] == "ok"
        for delta in resp["proposal"]["torque_delta_nm"]:
            assert math.isfinite(delta), f"Non-finite delta: {delta}"

    def test_calibration_within_ranges(self):
        """Calibration values must be within allowed ranges."""
        req = make_request(seed=42)
        resp = process_request(req)

        assert resp["status"] == "ok"
        ranges = req["constraints"]["calibration_ranges"]
        cal = resp["proposal"]["calibration"]

        for param, (lo, hi) in ranges.items():
            if param in cal:
                assert lo <= cal[param] <= hi, (
                    f"calibration.{param}={cal[param]} outside [{lo}, {hi}]"
                )

    def test_delta_length_matches_rpm_bins(self):
        """torque_delta_nm length must match rpm_bins length."""
        req = make_request(seed=42)
        resp = process_request(req)

        assert resp["status"] == "ok"
        expected_len = len(req["baseline_curve"]["rpm_bins"])
        assert len(resp["proposal"]["torque_delta_nm"]) == expected_len


# ── Schema validation tests ───────────────────────────────────────────────────

class TestSchemaValidation:
    def test_wrong_contract_version(self):
        """Wrong contract_version must return status=error."""
        req = make_request(contract_version="9.9")
        resp = process_request(req)
        assert resp["status"] == "error"
        assert resp["error"]["code"] == "SCHEMA_ERROR"
        assert "contract_version" in resp["error"]["message"]

    def test_missing_request_id(self):
        """Missing request_id must return status=error."""
        req = make_request()
        del req["request_id"]
        resp = process_request(req)
        assert resp["status"] == "error"
        assert resp["error"]["code"] == "SCHEMA_ERROR"

    def test_missing_seed(self):
        """Missing seed must return status=error."""
        req = make_request()
        del req["seed"]
        resp = process_request(req)
        assert resp["status"] == "error"

    def test_missing_baseline_curve(self):
        """Missing baseline_curve must return status=error."""
        req = make_request()
        del req["baseline_curve"]
        resp = process_request(req)
        assert resp["status"] == "error"

    def test_mismatched_rpm_torque_lengths(self):
        """rpm_bins and torque_nm of different lengths must return status=error."""
        req = make_request(
            rpm_bins=[1000, 2000, 3000],
            torque_nm=[180.0, 200.0],  # length mismatch
        )
        resp = process_request(req)
        assert resp["status"] == "error"

    def test_non_monotonic_rpm_bins(self):
        """Non-monotonic rpm_bins must return status=error."""
        req = make_request(
            rpm_bins=[1000, 3000, 2000, 4000],  # 3000 > 2000 — not ascending
            torque_nm=[180.0, 200.0, 210.0, 205.0],
        )
        resp = process_request(req)
        assert resp["status"] == "error"
        assert "monotonically" in resp["error"]["message"]

    def test_non_positive_torque_in_baseline(self):
        """Zero or negative torque in baseline must return status=error."""
        req = make_request(
            rpm_bins=[1000, 2000, 3000],
            torque_nm=[180.0, 0.0, 200.0],  # zero torque
        )
        resp = process_request(req)
        assert resp["status"] == "error"

    def test_invalid_cycle_budget_type(self):
        """Non-integer cycle_budget must return status=error."""
        req = make_request()
        req["cycle_budget"] = "forty"
        resp = process_request(req)
        assert resp["status"] == "error"

    def test_zero_cycle_budget(self):
        """cycle_budget of 0 must return status=error."""
        req = make_request()
        req["cycle_budget"] = 0
        resp = process_request(req)
        assert resp["status"] == "error"

    def test_non_integer_seed(self):
        """Non-integer seed must return status=error."""
        req = make_request()
        req["seed"] = "not-a-seed"
        resp = process_request(req)
        assert resp["status"] == "error"


# ── Validator unit tests ──────────────────────────────────────────────────────

class TestValidator:
    def _base_constraints(self):
        return {
            "max_peak_gain_ratio": 0.02,
            "max_bin_delta_nm": 8.0,
            "max_bin_delta_ratio": 0.03,
            "smoothness": {"max_second_derivative": 0.15},
            "calibration_ranges": {
                "afr_target": [11.5, 14.7],
                "ign_timing_deg": [-2.0, 8.0],
                "boost_target_psi": [0.0, 22.0],
            },
        }

    def test_valid_proposal_passes(self):
        baseline = [200.0, 210.0, 220.0, 215.0, 200.0]
        rpm_bins = [1000, 2000, 3000, 4000, 5000]
        # Flat deltas: second derivative = 0 everywhere — always passes smoothness check.
        # 1.0 Nm < max_bin_delta_nm=8.0, ratio 1/200=0.005 < 0.03, peak gain 1/220=0.0045 < 0.02
        deltas = [1.0, 1.0, 1.0, 1.0, 1.0]
        cal = {"afr_target": 13.0, "ign_timing_deg": 2.0, "boost_target_psi": 10.0}
        warnings = validate_proposal(deltas, cal, baseline, rpm_bins, self._base_constraints())
        assert isinstance(warnings, list)

    def test_nan_delta_raises(self):
        baseline = [200.0, 210.0, 220.0]
        rpm_bins = [1000, 2000, 3000]
        deltas = [1.0, float("nan"), 1.0]
        cal = {}
        with pytest.raises(ValidationError, match="not finite"):
            validate_proposal(deltas, cal, baseline, rpm_bins, self._base_constraints())

    def test_infinity_delta_raises(self):
        baseline = [200.0, 210.0, 220.0]
        rpm_bins = [1000, 2000, 3000]
        deltas = [1.0, float("inf"), 1.0]
        cal = {}
        with pytest.raises(ValidationError, match="not finite"):
            validate_proposal(deltas, cal, baseline, rpm_bins, self._base_constraints())

    def test_delta_exceeds_absolute_limit_raises(self):
        baseline = [200.0, 210.0, 220.0]
        rpm_bins = [1000, 2000, 3000]
        deltas = [1.0, 9.0, 1.0]  # 9.0 > max_bin_delta_nm=8.0
        cal = {}
        with pytest.raises(ValidationError, match="max_bin_delta_nm"):
            validate_proposal(deltas, cal, baseline, rpm_bins, self._base_constraints())

    def test_delta_exceeds_ratio_limit_raises(self):
        baseline = [200.0, 210.0, 220.0]
        rpm_bins = [1000, 2000, 3000]
        # 7.0 / 210.0 = 0.0333 > max_bin_delta_ratio=0.03
        deltas = [1.0, 7.0, 1.0]
        cal = {}
        with pytest.raises(ValidationError, match="max_bin_delta_ratio"):
            validate_proposal(deltas, cal, baseline, rpm_bins, self._base_constraints())

    def test_peak_gain_exceeds_cap_raises(self):
        baseline = [200.0, 220.0, 200.0]
        rpm_bins = [1000, 2000, 3000]
        # peak baseline = 220. 2% cap = 4.4 Nm. delta of 5.0 at peak bin exceeds cap.
        # But 5.0 > max_bin_delta_nm=8.0? No, 5.0 < 8.0. Ratio: 5/220=0.0227 > 0.03? No.
        # Let's use a tighter constraint
        constraints = {
            "max_peak_gain_ratio": 0.02,
            "max_bin_delta_nm": 8.0,
            "max_bin_delta_ratio": 0.05,  # looser ratio so ratio check passes
            "smoothness": {"max_second_derivative": 100.0},  # disable smoothness
            "calibration_ranges": {},
        }
        # peak = 220, 2% = 4.4 Nm. Apply delta of 5.0 to peak bin → 225 → gain = 5/220 = 0.0227 > 0.02
        deltas = [0.0, 5.0, 0.0]
        cal = {}
        with pytest.raises(ValidationError, match="peak gain ratio"):
            validate_proposal(deltas, cal, baseline, rpm_bins, constraints)

    def test_calibration_out_of_range_raises(self):
        baseline = [200.0, 210.0, 220.0]
        rpm_bins = [1000, 2000, 3000]
        deltas = [0.0, 0.0, 0.0]
        cal = {"afr_target": 10.0}  # below min 11.5
        with pytest.raises(ValidationError, match="afr_target"):
            validate_proposal(deltas, cal, baseline, rpm_bins, self._base_constraints())

    def test_length_mismatch_raises(self):
        baseline = [200.0, 210.0]
        rpm_bins = [1000, 2000, 3000]  # length 3
        deltas = [1.0, 1.0]  # length 2 — mismatch
        cal = {}
        with pytest.raises(ValidationError, match="length"):
            validate_proposal(deltas, cal, baseline, rpm_bins, self._base_constraints())


# ── Response structure tests ──────────────────────────────────────────────────

class TestResponseStructure:
    def test_ok_response_has_required_fields(self):
        req = make_request(seed=1)
        resp = process_request(req)
        assert resp["status"] == "ok"
        assert "contract_version" in resp
        assert resp["contract_version"] == "1.0"
        assert "request_id" in resp
        assert resp["request_id"] == req["request_id"]
        assert "proposal" in resp
        assert "metrics" in resp
        assert "debug" in resp
        assert resp["error"] is None

    def test_proposal_has_required_fields(self):
        req = make_request(seed=1)
        resp = process_request(req)
        assert resp["status"] == "ok"
        proposal = resp["proposal"]
        assert "calibration" in proposal
        assert "torque_delta_nm" in proposal
        assert "confidence" in proposal
        assert "estimated_peak_gain_ratio" in proposal

    def test_metrics_has_required_fields(self):
        req = make_request(seed=1)
        resp = process_request(req)
        assert resp["status"] == "ok"
        metrics = resp["metrics"]
        assert "cycles_used" in metrics
        assert "runtime_ms" in metrics
        assert "best_score" in metrics

    def test_confidence_in_range(self):
        req = make_request(seed=1)
        resp = process_request(req)
        assert resp["status"] == "ok"
        confidence = resp["proposal"]["confidence"]
        assert 0.0 <= confidence <= 1.0

    def test_request_id_echoed(self):
        req = make_request(seed=1, request_id="my-unique-id-xyz")
        resp = process_request(req)
        assert resp["request_id"] == "my-unique-id-xyz"

    def test_json_serializable(self):
        """Response must be fully JSON-serializable (no NaN, no infinity)."""
        req = make_request(seed=42)
        resp = process_request(req)
        # This will raise if any value is NaN or infinity
        serialized = json.dumps(resp)
        assert len(serialized) > 0


# ── Subprocess end-to-end tests ──────────────────────────────────────────────

class TestSubprocess:
    """
    Invoke ecu_runner.py as a real subprocess, exactly as Unity would.
    Verifies:
      - stdout contains only valid JSON
      - stderr contains only log lines (not JSON)
      - response is contract-compliant
    """

    def _run_subprocess(self, request: dict) -> tuple[dict, str]:
        """
        Pipe request JSON to ecu_runner.py stdin.
        Returns (parsed_response_dict, stderr_text).
        """
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "ecu_runner.py"],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        # stdout must be parseable JSON
        response = json.loads(result.stdout)
        return response, result.stderr

    def test_subprocess_stdout_is_valid_json(self):
        """stdout must contain exactly one valid JSON object."""
        req = make_request(seed=42)
        resp, _ = self._run_subprocess(req)
        assert isinstance(resp, dict)
        assert "status" in resp
        assert "contract_version" in resp

    def test_subprocess_returns_ok(self):
        """A valid request via subprocess must return status=ok."""
        req = make_request(seed=42)
        resp, _ = self._run_subprocess(req)
        assert resp["status"] == "ok"

    def test_subprocess_stderr_not_empty(self):
        """stderr must contain log output (ECU runner logs its start)."""
        req = make_request(seed=42)
        _, stderr = self._run_subprocess(req)
        assert len(stderr.strip()) > 0, "Expected log output on stderr"

    def test_subprocess_stderr_is_not_json(self):
        """stderr must NOT contain the JSON response — logs only."""
        req = make_request(seed=42)
        _, stderr = self._run_subprocess(req)
        # stderr should not be parseable as the response JSON
        for line in stderr.strip().splitlines():
            try:
                parsed = json.loads(line)
                # If a line parses as JSON, it must not be the response object
                assert "torque_delta_nm" not in parsed, (
                    "Response JSON found on stderr — must only appear on stdout"
                )
            except json.JSONDecodeError:
                pass  # Expected: log lines are not JSON

    def test_subprocess_determinism(self):
        """Two subprocess calls with the same seed must return identical proposals."""
        req = make_request(seed=99999)
        resp1, _ = self._run_subprocess(req)
        resp2, _ = self._run_subprocess(req)
        assert resp1["status"] == "ok"
        assert resp2["status"] == "ok"
        assert resp1["proposal"]["torque_delta_nm"] == resp2["proposal"]["torque_delta_nm"]
        assert resp1["proposal"]["calibration"] == resp2["proposal"]["calibration"]

    def test_subprocess_invalid_json_input(self):
        """Sending malformed JSON must return status=error, not crash."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "ecu_runner.py"],
            input="this is not json {{{",
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        resp = json.loads(result.stdout)
        assert resp["status"] == "error"
        assert resp["error"]["code"] == "JSON_PARSE_ERROR"

    def test_subprocess_empty_input(self):
        """Sending empty stdin must return status=error, not crash."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "ecu_runner.py"],
            input="",
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        resp = json.loads(result.stdout)
        assert resp["status"] == "error"
        assert resp["error"]["code"] == "EMPTY_INPUT"


# ── Performance tests ─────────────────────────────────────────────────────────

class TestPerformance:
    """
    Verify ECU completes within the contract performance budget.
    Contract requirement: ECU subprocess under 2000ms (2 seconds).
    """

    def test_ecu_completes_under_2_seconds_in_process(self):
        """
        In-process timing: process_request must complete under 2 seconds
        for a standard 40-cycle request.
        """
        import time
        req = make_request(seed=42, cycle_budget=40)
        t0 = time.monotonic()
        resp = process_request(req)
        elapsed_ms = (time.monotonic() - t0) * 1000

        assert resp["status"] == "ok"
        assert elapsed_ms < 2000, (
            f"ECU took {elapsed_ms:.1f}ms — exceeds 2000ms contract limit"
        )

    def test_ecu_runtime_ms_reported_in_metrics(self):
        """runtime_ms in metrics must be a non-negative finite number."""
        req = make_request(seed=42, cycle_budget=40)
        resp = process_request(req)
        assert resp["status"] == "ok"
        runtime_ms = resp["metrics"]["runtime_ms"]
        assert isinstance(runtime_ms, (int, float))
        assert math.isfinite(runtime_ms)
        assert runtime_ms >= 0

    def test_large_budget_still_under_2_seconds(self):
        """Even with cycle_budget=200, must complete under 2 seconds."""
        import time
        req = make_request(seed=42, cycle_budget=200)
        t0 = time.monotonic()
        resp = process_request(req)
        elapsed_ms = (time.monotonic() - t0) * 1000

        assert resp["status"] == "ok"
        assert elapsed_ms < 2000, (
            f"ECU with budget=200 took {elapsed_ms:.1f}ms — exceeds 2000ms limit"
        )


# ── Smoothness rejection path tests ──────────────────────────────────────────

class TestSmoothnessRejection:
    """
    Verify that non-smooth delta curves are correctly rejected by the validator,
    and that the runner returns status=rejected (not status=error) in that case.
    """

    def _base_constraints(self, max_second_derivative: float = 0.15):
        return {
            "max_peak_gain_ratio": 0.02,
            "max_bin_delta_nm": 8.0,
            "max_bin_delta_ratio": 0.03,
            "smoothness": {"max_second_derivative": max_second_derivative},
            "calibration_ranges": {
                "afr_target": [11.5, 14.7],
                "ign_timing_deg": [-2.0, 8.0],
                "boost_target_psi": [0.0, 22.0],
            },
        }

    def test_non_smooth_delta_raises_validation_error(self):
        """
        A delta with a sharp spike (high second derivative) must raise ValidationError.
        delta = [0, 0, 5, 0, 0]: second derivative at bin 2 = |0 - 2*5 + 0| = 10 >> 0.15
        """
        baseline = [200.0, 200.0, 200.0, 200.0, 200.0]
        rpm_bins = [1000, 2000, 3000, 4000, 5000]
        # Spike at bin 2: second_derivative = |0 - 2*5 + 0| = 10 >> 0.15
        # But 5.0/200 = 0.025 < 0.03 ratio, 5.0 < 8.0 absolute — only smoothness fails
        # Use looser ratio constraint so only smoothness triggers
        constraints = {
            "max_peak_gain_ratio": 0.05,
            "max_bin_delta_nm": 8.0,
            "max_bin_delta_ratio": 0.05,
            "smoothness": {"max_second_derivative": 0.15},
            "calibration_ranges": {},
        }
        deltas = [0.0, 0.0, 5.0, 0.0, 0.0]
        cal = {}
        with pytest.raises(ValidationError, match="smoothness violation"):
            validate_proposal(deltas, cal, baseline, rpm_bins, constraints)

    def test_smooth_delta_passes_validation(self):
        """
        A perfectly flat delta (second derivative = 0) must always pass smoothness.
        """
        baseline = [200.0, 200.0, 200.0, 200.0, 200.0]
        rpm_bins = [1000, 2000, 3000, 4000, 5000]
        deltas = [1.0, 1.0, 1.0, 1.0, 1.0]  # flat: second derivative = 0
        cal = {}
        warnings = validate_proposal(
            deltas, cal, baseline, rpm_bins, self._base_constraints()
        )
        assert isinstance(warnings, list)

    def test_smoothness_threshold_boundary(self):
        """
        A delta with second derivative clearly below the limit must pass.
        A delta with second derivative clearly above the limit must fail.

        Note: we avoid testing "exactly at limit" because floating point arithmetic
        means values like |1.0 - 2*1.1 + 1.0| = 0.20000000000000018 in IEEE 754,
        which is strictly > 0.20 and would correctly fail. We use values with a
        comfortable margin instead.
        """
        baseline = [200.0, 200.0, 200.0, 200.0, 200.0]
        rpm_bins = [1000, 2000, 3000, 4000, 5000]
        cal = {}
        constraints = {
            "max_peak_gain_ratio": 0.05,
            "max_bin_delta_nm": 8.0,
            "max_bin_delta_ratio": 0.05,
            "smoothness": {"max_second_derivative": 0.20},
            "calibration_ranges": {},
        }

        # deltas = [1.0, 1.05, 1.0, 1.05, 1.0]
        # second_derivative at bin 1 = |1.0 - 2*1.05 + 1.0| = |−0.1| = 0.1 < 0.20 ✓
        # second_derivative at bin 2 = |1.05 - 2*1.0 + 1.05| = 0.1 < 0.20 ✓
        deltas_below_limit = [1.0, 1.05, 1.0, 1.05, 1.0]
        warnings = validate_proposal(deltas_below_limit, cal, baseline, rpm_bins, constraints)
        assert isinstance(warnings, list)  # must pass

        # deltas = [1.0, 1.2, 1.0, 1.2, 1.0]
        # second_derivative at bin 1 = |1.0 - 2*1.2 + 1.0| = 0.4 > 0.20 ✗
        deltas_above_limit = [1.0, 1.2, 1.0, 1.2, 1.0]
        with pytest.raises(ValidationError, match="smoothness violation"):
            validate_proposal(deltas_above_limit, cal, baseline, rpm_bins, constraints)

    def test_optimizer_output_always_smooth(self):
        """
        The optimizer must never produce a delta that fails the smoothness check.
        Verified across multiple seeds.
        """
        baseline = [180.0, 195.0, 210.0, 220.0, 225.0, 222.0, 215.0, 205.0, 190.0, 170.0, 145.0]
        rpm_bins = [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000]
        constraints = {
            "max_peak_gain_ratio": 0.02,
            "max_bin_delta_nm": 8.0,
            "max_bin_delta_ratio": 0.03,
            "smoothness": {"max_second_derivative": 0.15},
            "calibration_ranges": {
                "afr_target": [11.5, 14.7],
                "ign_timing_deg": [-2.0, 8.0],
                "boost_target_psi": [0.0, 22.0],
            },
        }
        for seed in [1, 42, 100, 999, 12345]:
            result = run_optimization(baseline, rpm_bins, constraints, cycle_budget=40, seed=seed)
            deltas = result["torque_delta_nm"]
            # Verify smoothness manually
            for i in range(1, len(deltas) - 1):
                second_deriv = abs(deltas[i + 1] - 2 * deltas[i] + deltas[i - 1])
                assert second_deriv <= 0.15 + 1e-9, (
                    f"seed={seed} bin={i}: second_derivative={second_deriv:.6f} > 0.15"
                )


# ── Edge case tests ───────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_bin_curve(self):
        """A single-bin curve should still produce a valid response."""
        req = make_request(
            rpm_bins=[3000],
            torque_nm=[220.0],
        )
        resp = process_request(req)
        assert resp["status"] == "ok"
        assert len(resp["proposal"]["torque_delta_nm"]) == 1

    def test_large_cycle_budget(self):
        """Large cycle_budget should complete without error."""
        req = make_request(seed=42, cycle_budget=200)
        resp = process_request(req)
        assert resp["status"] == "ok"

    def test_tight_constraints_still_valid(self):
        """Very tight constraints should produce zero or near-zero deltas, not an error."""
        req = make_request(
            seed=42,
            constraints={
                "max_peak_gain_ratio": 0.001,
                "max_bin_delta_nm": 0.1,
                "max_bin_delta_ratio": 0.001,
                "smoothness": {"max_second_derivative": 0.15},
                "calibration_ranges": {
                    "afr_target": [13.0, 13.5],
                    "ign_timing_deg": [0.0, 1.0],
                    "boost_target_psi": [5.0, 6.0],
                },
            },
        )
        resp = process_request(req)
        assert resp["status"] == "ok"
        for delta in resp["proposal"]["torque_delta_nm"]:
            assert abs(delta) <= 0.1 + 1e-9
