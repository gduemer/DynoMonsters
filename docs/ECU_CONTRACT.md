# ECU Contract: Unity <-> Python

## 1. Transport
Phase 0 transport is subprocess stdin/stdout using JSON.

- Unity runs: python ecu_runner.py
- Unity writes one JSON request to stdin
- Python writes one JSON response to stdout
- Python logs to stderr

## 2. Versioning
Every request and response includes:
- contract_version: "1.0"

Any breaking change must bump the version.

## 3. Request JSON Schema (informal)

{
  "contract_version": "1.0",
  "request_id": "uuid-or-string",
  "seed": 123456,
  "cycle_budget": 40,

  "vehicle": {
    "vehicle_id": "string",
    "engine_family": "string",
    "aspiration": "NA|Turbo|Supercharged",
    "drivetrain": "FWD|RWD|AWD"
  },

  "environment": {
    "biome_id": "string",
    "altitude_m": 0.0,
    "ambient_temp_c": 25.0
  },

  "street_cred": {
    "level": 1,
    "modifier": 1.0
  },

  "baseline_curve": {
    "rpm_bins": [1000, 1500, 2000, ...],
    "torque_nm": [180.0, 195.0, 210.0, ...]
  },

  "constraints": {
    "max_peak_gain_ratio": 0.02,
    "max_bin_delta_nm": 8.0,
    "max_bin_delta_ratio": 0.03,
    "max_total_variation_ratio": 0.02,
    "smoothness": {
      "max_second_derivative": 0.15
    },
    "calibration_ranges": {
      "afr_target": [11.5, 14.7],
      "ign_timing_deg": [-2.0, 8.0],
      "boost_target_psi": [0.0, 22.0]
    }
  },

  "parts": [
    {
      "part_id": "string",
      "category": "turbo|intake|exhaust|cooling|fuel|ignition|ecu",
      "potential": {
        "boost_efficiency": [0.95, 1.05],
        "cooling_multiplier": [0.9, 1.1]
      }
    }
  ]
}

Notes:
- Unity always sends a complete baseline curve and constraints.
- Python must not invent RPM bins. It can propose deltas for the same bins only.
- cycle_budget is already computed by Unity based on Street Cred and rules.

## 4. Response JSON Schema (informal)

{
  "contract_version": "1.0",
  "request_id": "same-as-request",
  "status": "ok|rejected|error",

  "proposal": {
    "calibration": {
      "afr_target": 12.8,
      "ign_timing_deg": 4.0,
      "boost_target_psi": 14.0
    },
    "torque_delta_nm": [0.0, 1.2, 2.8, ...],
    "confidence": 0.0,
    "estimated_peak_gain_ratio": 0.0
  },

  "metrics": {
    "cycles_used": 40,
    "runtime_ms": 120,
    "best_score": 0.82
  },

  "debug": {
    "notes": ["string", "string"],
    "warnings": ["string"]
  },

  "error": {
    "code": "string",
    "message": "string"
  }
}

Rules:
- status="ok" only if proposal is present and internally consistent.
- If Python cannot produce a valid proposal, it should return:
  status="rejected" with warnings, and proposal may be null.
- On exceptions, return status="error" and fill error fields.
- Never output NaN or infinity.

## 5. Unity Validation Rules (must pass)
Unity rejects the proposal if:
- torque_delta length does not match rpm_bins length
- any torque_delta is NaN or infinity
- any abs(delta) exceeds max_bin_delta_nm
- any abs(delta)/baseline exceeds max_bin_delta_ratio for that bin
- applying delta yields peak gain above max_peak_gain_ratio
- curve smoothness fails max_second_derivative check
- calibration values out of calibration_ranges

If rejected, Unity applies baseline tune and logs the reason.

## 6. Determinism
Given identical request JSON and seed:
- Python must return identical response JSON proposal fields.
- runtime_ms may vary. That is allowed.

## 7. Logging
Python writes logs to stderr only, never stdout.
Stdout must contain only the JSON response.