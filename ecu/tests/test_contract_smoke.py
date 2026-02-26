"""Contract smoke test — validates the full stdin→stdout ECU pipeline.

This is the test referenced by CI workflow 03-ecu-contract-smoke.yml.
"""

import json

from ecu.ecu_runner import run

# A minimal but complete v1.0 request.
_SAMPLE_REQUEST = {
    "contract_version": "1.0",
    "request_id": "smoke-test-001",
    "seed": 12345,
    "cycle_budget": 20,
    "vehicle": {
        "vehicle_id": "test-vehicle",
        "engine_family": "inline-4",
        "aspiration": "Turbo",
        "drivetrain": "AWD",
    },
    "environment": {
        "biome_id": "urban-flat",
        "altitude_m": 150.0,
        "ambient_temp_c": 25.0,
    },
    "street_cred": {
        "level": 1,
        "modifier": 1.0,
    },
    "baseline_curve": {
        "rpm_bins": [1000, 2000, 3000, 4000, 5000, 6000, 7000],
        "torque_nm": [120.0, 180.0, 220.0, 240.0, 235.0, 210.0, 170.0],
    },
    "constraints": {
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
    },
    "parts": [],
}


class TestContractSmoke:
    def test_ok_response_structure(self):
        """A valid request must yield status=ok with all required keys."""
        resp_json = run(json.dumps(_SAMPLE_REQUEST))
        resp = json.loads(resp_json)

        assert resp["contract_version"] == "1.0"
        assert resp["request_id"] == "smoke-test-001"
        assert resp["status"] == "ok"
        assert "proposal" in resp
        assert "metrics" in resp
        assert "debug" in resp

    def test_proposal_fields(self):
        """Proposal must contain calibration, torque_delta_nm, etc."""
        resp = json.loads(run(json.dumps(_SAMPLE_REQUEST)))
        p = resp["proposal"]
        assert "calibration" in p
        assert "torque_delta_nm" in p
        assert "confidence" in p
        assert "estimated_peak_gain_ratio" in p

    def test_delta_length_matches_bins(self):
        """torque_delta_nm must have the same length as rpm_bins."""
        resp = json.loads(run(json.dumps(_SAMPLE_REQUEST)))
        n_bins = len(_SAMPLE_REQUEST["baseline_curve"]["rpm_bins"])
        assert len(resp["proposal"]["torque_delta_nm"]) == n_bins

    def test_deltas_within_constraint(self):
        """No delta may exceed max_bin_delta_nm."""
        resp = json.loads(run(json.dumps(_SAMPLE_REQUEST)))
        max_delta = _SAMPLE_REQUEST["constraints"]["max_bin_delta_nm"]
        for d in resp["proposal"]["torque_delta_nm"]:
            assert abs(d) <= max_delta + 1e-9

    def test_peak_gain_within_cap(self):
        """Peak gain must not exceed max_peak_gain_ratio."""
        resp = json.loads(run(json.dumps(_SAMPLE_REQUEST)))
        baseline = _SAMPLE_REQUEST["baseline_curve"]["torque_nm"]
        deltas = resp["proposal"]["torque_delta_nm"]
        proposed = [t + d for t, d in zip(baseline, deltas)]
        gain = (max(proposed) - max(baseline)) / max(baseline)
        assert gain <= _SAMPLE_REQUEST["constraints"]["max_peak_gain_ratio"] + 1e-9

    def test_determinism(self):
        """Same request must produce identical proposal."""
        r1 = json.loads(run(json.dumps(_SAMPLE_REQUEST)))
        r2 = json.loads(run(json.dumps(_SAMPLE_REQUEST)))
        assert r1["proposal"] == r2["proposal"]

    def test_invalid_request_returns_error(self):
        """A request missing required keys must return status=error."""
        bad = {"contract_version": "1.0", "request_id": "bad"}
        resp = json.loads(run(json.dumps(bad)))
        assert resp["status"] == "error"
        assert resp["error"]["code"] == "INVALID_REQUEST"

    def test_garbage_json_returns_error(self):
        """Non-JSON input must return a JSON error response."""
        resp = json.loads(run("not json at all"))
        assert resp["status"] == "error"
        assert resp["error"]["code"] == "JSON_PARSE"

    def test_calibration_within_ranges(self):
        """Calibration values must respect the constraint ranges."""
        resp = json.loads(run(json.dumps(_SAMPLE_REQUEST)))
        cal = resp["proposal"]["calibration"]
        ranges = _SAMPLE_REQUEST["constraints"]["calibration_ranges"]
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
