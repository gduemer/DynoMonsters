"""ECU runner — subprocess entry point.

Usage (Phase 0):
    echo '{"contract_version":"1.0", ...}' | python -m ecu.ecu_runner

Reads one JSON request from stdin, writes one JSON response to stdout.
All logs go to stderr.
"""

from __future__ import annotations

import json
import logging
import sys
import time

from ecu.contract import (
    build_error_response,
    build_ok_response,
    validate_request,
    validate_response,
)
from ecu.ecu_optimizer import optimize

# Structured logging → stderr only.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ecu_runner")


def run(request_json: str) -> str:
    """Process a single ECU request and return the JSON response string."""
    request_id = "unknown"
    try:
        req = json.loads(request_json)
        request_id = req.get("request_id", request_id)

        errors = validate_request(req)
        if errors:
            logger.warning("Request validation failed: %s", errors)
            resp = build_error_response(
                request_id=request_id,
                code="INVALID_REQUEST",
                message="; ".join(errors),
            )
            return json.dumps(resp)

        start = time.monotonic()
        result = optimize(
            rpm_bins=req["baseline_curve"]["rpm_bins"],
            baseline_torque=req["baseline_curve"]["torque_nm"],
            constraints=req["constraints"],
            cycle_budget=req["cycle_budget"],
            seed=req["seed"],
            parts=req.get("parts"),
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        resp = build_ok_response(
            request_id=request_id,
            calibration=result["calibration"],
            torque_delta_nm=result["torque_delta_nm"],
            confidence=result["confidence"],
            estimated_peak_gain_ratio=result["estimated_peak_gain_ratio"],
            cycles_used=result["cycles_used"],
            runtime_ms=round(elapsed_ms, 2),
            best_score=result["best_score"],
            notes=result["notes"],
            warnings=result["warnings"],
        )

        resp_errors = validate_response(resp)
        if resp_errors:
            logger.error("Self-validation failed: %s", resp_errors)
            resp = build_error_response(
                request_id=request_id,
                code="INTERNAL_VALIDATION",
                message="; ".join(resp_errors),
            )

        return json.dumps(resp)

    except json.JSONDecodeError as exc:
        logger.exception("JSON parse error")
        return json.dumps(
            build_error_response(request_id, "JSON_PARSE", str(exc))
        )
    except Exception as exc:
        logger.exception("Unexpected error")
        return json.dumps(
            build_error_response(request_id, "INTERNAL_ERROR", str(exc))
        )


def main() -> None:
    """Read from stdin, write to stdout."""
    request_json = sys.stdin.read()
    response_json = run(request_json)
    sys.stdout.write(response_json)
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
