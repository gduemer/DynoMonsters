"""
ecu_runner.py

ECU subprocess entry point for DynoMonsters.

Transport: Unity writes one JSON request to stdin.
           Python writes one JSON response to stdout.
           All logs go to stderr.

Contract version: 1.0  (see docs/ECU_CONTRACT.md)

Unity is authoritative. This service proposes only.
"""

import json
import logging
import math
import sys
import time
import traceback
from typing import Any

# ── Logging setup ─────────────────────────────────────────────────────────────
# All logs MUST go to stderr. stdout is reserved for the JSON response only.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ecu_runner")

# ── Import ECU modules ────────────────────────────────────────────────────────
from ecu.optimizer import run_optimization
from ecu.validator import validate_proposal, ValidationError

CONTRACT_VERSION = "1.0"


# ── Response builders ─────────────────────────────────────────────────────────

def _error_response(request_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "error",
        "proposal": None,
        "metrics": None,
        "debug": {"notes": [], "warnings": []},
        "error": {"code": code, "message": message},
    }


def _rejected_response(
    request_id: str,
    warnings: list[str],
    notes: list[str],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "rejected",
        "proposal": None,
        "metrics": None,
        "debug": {"notes": notes, "warnings": warnings},
        "error": None,
    }


def _ok_response(
    request_id: str,
    proposal: dict[str, Any],
    metrics: dict[str, Any],
    warnings: list[str],
    notes: list[str],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "ok",
        "proposal": proposal,
        "metrics": metrics,
        "debug": {"notes": notes, "warnings": warnings},
        "error": None,
    }


# ── Input validation helpers ──────────────────────────────────────────────────

def _require_key(obj: dict, key: str, context: str) -> Any:
    if key not in obj:
        raise ValueError(f"Missing required field '{key}' in {context}")
    return obj[key]


def _validate_request_schema(req: dict) -> None:
    """
    Validate the top-level structure of the incoming request.
    Raises ValueError with a descriptive message on any violation.
    """
    version = _require_key(req, "contract_version", "request")
    if version != CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported contract_version '{version}'. Expected '{CONTRACT_VERSION}'"
        )

    _require_key(req, "request_id", "request")
    _require_key(req, "seed", "request")
    _require_key(req, "cycle_budget", "request")

    baseline = _require_key(req, "baseline_curve", "request")
    rpm_bins = _require_key(baseline, "rpm_bins", "baseline_curve")
    torque_nm = _require_key(baseline, "torque_nm", "baseline_curve")

    if not isinstance(rpm_bins, list) or len(rpm_bins) == 0:
        raise ValueError("baseline_curve.rpm_bins must be a non-empty list")
    if not isinstance(torque_nm, list) or len(torque_nm) == 0:
        raise ValueError("baseline_curve.torque_nm must be a non-empty list")
    if len(rpm_bins) != len(torque_nm):
        raise ValueError(
            f"rpm_bins length {len(rpm_bins)} != torque_nm length {len(torque_nm)}"
        )

    # Validate rpm_bins is monotonically ascending
    for i in range(1, len(rpm_bins)):
        if rpm_bins[i] <= rpm_bins[i - 1]:
            raise ValueError(
                f"rpm_bins must be monotonically ascending: "
                f"rpm_bins[{i-1}]={rpm_bins[i-1]} >= rpm_bins[{i}]={rpm_bins[i]}"
            )

    # Validate all torque values are finite and positive
    for i, t in enumerate(torque_nm):
        if not math.isfinite(t) or t <= 0:
            raise ValueError(
                f"baseline_curve.torque_nm[{i}]={t} must be finite and positive"
            )

    _require_key(req, "constraints", "request")

    cycle_budget = req["cycle_budget"]
    if not isinstance(cycle_budget, int) or cycle_budget < 1:
        raise ValueError(f"cycle_budget must be a positive integer, got {cycle_budget!r}")

    seed = req["seed"]
    if not isinstance(seed, int):
        raise ValueError(f"seed must be an integer, got {seed!r}")


# ── Main processing ───────────────────────────────────────────────────────────

def process_request(req: dict) -> dict[str, Any]:
    """
    Core processing pipeline.
    Returns a fully-formed response dict.
    """
    request_id: str = req.get("request_id", "unknown")
    t_start = time.monotonic()

    # ── Schema validation ─────────────────────────────────────────────────────
    try:
        _validate_request_schema(req)
    except ValueError as exc:
        logger.warning("Request schema validation failed: %s", exc)
        return _error_response(request_id, "SCHEMA_ERROR", str(exc))

    seed: int = req["seed"]
    cycle_budget: int = req["cycle_budget"]
    baseline_curve: dict = req["baseline_curve"]
    rpm_bins: list[int] = baseline_curve["rpm_bins"]
    baseline_torque_nm: list[float] = [float(t) for t in baseline_curve["torque_nm"]]
    constraints: dict = req["constraints"]

    logger.info(
        "Processing request_id=%s seed=%d cycle_budget=%d bins=%d",
        request_id, seed, cycle_budget, len(rpm_bins),
    )

    # ── Run optimizer ─────────────────────────────────────────────────────────
    try:
        result = run_optimization(
            baseline_torque_nm=baseline_torque_nm,
            rpm_bins=rpm_bins,
            constraints=constraints,
            cycle_budget=cycle_budget,
            seed=seed,
        )
    except Exception as exc:
        logger.error("Optimizer raised an unexpected error: %s", exc, exc_info=True)
        return _error_response(request_id, "OPTIMIZER_ERROR", str(exc))

    torque_delta_nm: list[float] = result["torque_delta_nm"]
    calibration: dict[str, float] = result["calibration"]
    warnings: list[str] = result["warnings"]
    cycles_used: int = result["cycles_used"]
    best_score: float = result["best_score"]

    # ── Final self-validation (mirrors Unity's checks) ────────────────────────
    try:
        final_warnings = validate_proposal(
            torque_delta_nm=torque_delta_nm,
            calibration=calibration,
            baseline_torque_nm=baseline_torque_nm,
            rpm_bins=rpm_bins,
            constraints=constraints,
        )
        warnings = list(set(warnings + final_warnings))
    except ValidationError as exc:
        logger.warning("Final validation rejected proposal: %s", exc)
        return _rejected_response(
            request_id,
            warnings=[str(exc)],
            notes=["Proposal failed final self-validation. Returning rejected."],
        )

    # ── Check for any NaN/inf in output (hard safety gate) ───────────────────
    for i, delta in enumerate(torque_delta_nm):
        if not math.isfinite(delta):
            logger.error("Non-finite value in torque_delta_nm[%d]: %s", i, delta)
            return _error_response(
                request_id,
                "NON_FINITE_OUTPUT",
                f"torque_delta_nm[{i}] is not finite: {delta}",
            )

    t_end = time.monotonic()
    runtime_ms = round((t_end - t_start) * 1000, 2)

    proposal = {
        "calibration": calibration,
        "torque_delta_nm": torque_delta_nm,
        "confidence": result["confidence"],
        "estimated_peak_gain_ratio": result["estimated_peak_gain_ratio"],
    }

    metrics = {
        "cycles_used": cycles_used,
        "runtime_ms": runtime_ms,
        "best_score": best_score,
    }

    notes = [
        f"ECU stub v{CONTRACT_VERSION}",
        f"Optimization completed in {cycles_used} cycles",
    ]

    logger.info(
        "Request %s complete: status=ok runtime_ms=%.2f peak_gain=%.4f",
        request_id,
        runtime_ms,
        result["estimated_peak_gain_ratio"],
    )

    return _ok_response(request_id, proposal, metrics, warnings, notes)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("ECU runner started. Waiting for request on stdin.")

    try:
        raw_input = sys.stdin.read()
    except Exception as exc:
        response = _error_response("unknown", "STDIN_READ_ERROR", str(exc))
        print(json.dumps(response), flush=True)
        sys.exit(1)

    if not raw_input.strip():
        response = _error_response("unknown", "EMPTY_INPUT", "stdin was empty")
        print(json.dumps(response), flush=True)
        sys.exit(1)

    try:
        request = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from stdin: %s", exc)
        response = _error_response("unknown", "JSON_PARSE_ERROR", str(exc))
        print(json.dumps(response), flush=True)
        sys.exit(1)

    if not isinstance(request, dict):
        response = _error_response(
            "unknown", "INVALID_REQUEST_TYPE", "Request must be a JSON object"
        )
        print(json.dumps(response), flush=True)
        sys.exit(1)

    try:
        response = process_request(request)
    except Exception as exc:
        logger.critical("Unhandled exception in process_request: %s", exc, exc_info=True)
        request_id = request.get("request_id", "unknown") if isinstance(request, dict) else "unknown"
        response = _error_response(request_id, "UNHANDLED_ERROR", str(exc))

    # stdout must contain ONLY the JSON response
    print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
