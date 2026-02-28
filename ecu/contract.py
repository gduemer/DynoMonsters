"""ECU contract validation — v1.0.

Validates request and response JSON structures per docs/ECU_CONTRACT.md.
"""

from __future__ import annotations

import math
from typing import Any

CONTRACT_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

_REQUIRED_REQUEST_KEYS = {
    "contract_version",
    "request_id",
    "seed",
    "cycle_budget",
    "vehicle",
    "environment",
    "street_cred",
    "baseline_curve",
    "constraints",
}

_ASPIRATION_VALUES = {"NA", "Turbo", "Supercharged"}
_DRIVETRAIN_VALUES = {"FWD", "RWD", "AWD"}


def validate_request(req: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty means valid)."""
    errors: list[str] = []

    # Top-level keys
    missing = _REQUIRED_REQUEST_KEYS - set(req.keys())
    if missing:
        errors.append(f"Missing top-level keys: {sorted(missing)}")
        return errors  # can't validate further

    if req["contract_version"] != CONTRACT_VERSION:
        errors.append(
            f"Unsupported contract_version: {req['contract_version']}"
        )

    # Seed / budget
    if not isinstance(req["seed"], int):
        errors.append("seed must be an integer")
    if not isinstance(req["cycle_budget"], int) or req["cycle_budget"] < 1:
        errors.append("cycle_budget must be a positive integer")

    # Vehicle
    v = req.get("vehicle", {})
    if v.get("aspiration") not in _ASPIRATION_VALUES:
        errors.append(
            f"Invalid aspiration: {v.get('aspiration')} "
            f"(expected one of {_ASPIRATION_VALUES})"
        )
    if v.get("drivetrain") not in _DRIVETRAIN_VALUES:
        errors.append(
            f"Invalid drivetrain: {v.get('drivetrain')} "
            f"(expected one of {_DRIVETRAIN_VALUES})"
        )

    # Baseline curve
    bc = req.get("baseline_curve", {})
    rpm_bins = bc.get("rpm_bins", [])
    torque_nm = bc.get("torque_nm", [])
    if not rpm_bins:
        errors.append("baseline_curve.rpm_bins is empty")
    if len(rpm_bins) != len(torque_nm):
        errors.append("baseline_curve array length mismatch")
    for val in torque_nm:
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            errors.append(f"Non-finite torque value: {val}")
            break

    # Constraints — spot check required sub-keys
    c = req.get("constraints", {})
    for key in (
        "max_peak_gain_ratio",
        "max_bin_delta_nm",
        "max_bin_delta_ratio",
    ):
        if key not in c:
            errors.append(f"Missing constraint: {key}")

    return errors


# ---------------------------------------------------------------------------
# Response building helpers
# ---------------------------------------------------------------------------


def build_ok_response(
    request_id: str,
    calibration: dict[str, float],
    torque_delta_nm: list[float],
    confidence: float,
    estimated_peak_gain_ratio: float,
    cycles_used: int,
    runtime_ms: float,
    best_score: float,
    notes: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a well-formed "ok" response dict."""
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "ok",
        "proposal": {
            "calibration": calibration,
            "torque_delta_nm": torque_delta_nm,
            "confidence": confidence,
            "estimated_peak_gain_ratio": estimated_peak_gain_ratio,
        },
        "metrics": {
            "cycles_used": cycles_used,
            "runtime_ms": runtime_ms,
            "best_score": best_score,
        },
        "debug": {
            "notes": notes or [],
            "warnings": warnings or [],
        },
    }


def build_error_response(
    request_id: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    """Build a well-formed "error" response dict."""
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "error",
        "proposal": None,
        "metrics": None,
        "debug": {"notes": [], "warnings": []},
        "error": {"code": code, "message": message},
    }


def build_rejected_response(
    request_id: str,
    warnings: list[str],
) -> dict[str, Any]:
    """Build a well-formed "rejected" response dict."""
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": "rejected",
        "proposal": None,
        "metrics": None,
        "debug": {"notes": [], "warnings": warnings},
    }


# ---------------------------------------------------------------------------
# Response self-check (Python-side, before sending)
# ---------------------------------------------------------------------------


def validate_response(resp: dict[str, Any]) -> list[str]:
    """Basic self-validation of a response dict before serialising."""
    errors: list[str] = []
    if resp.get("contract_version") != CONTRACT_VERSION:
        errors.append("Bad contract_version in response")
    if resp.get("status") not in ("ok", "rejected", "error"):
        errors.append(f"Invalid status: {resp.get('status')}")
    if resp["status"] == "ok":
        proposal = resp.get("proposal")
        if proposal is None:
            errors.append("status=ok but proposal is None")
        else:
            deltas = proposal.get("torque_delta_nm", [])
            for i, d in enumerate(deltas):
                if not isinstance(d, (int, float)) or not math.isfinite(d):
                    errors.append(f"Non-finite delta at index {i}: {d}")
                    break
    return errors
