"""NHTSA vPIC API fetch script for DynoMonsters.

Fetches real vehicle base stats from the NHTSA Vehicle Product Information
Catalog (vPIC) API and constructs ``Car`` instances from the results.

API reference: https://vpic.nhtsa.dot.gov/api/

Notes
-----
- Uses ``urllib.request`` (stdlib only — no external dependencies).
- NHTSA vPIC does not expose HP or torque directly.  Base torque is
  estimated from engine displacement using a lookup table.
- All network calls go to stderr logs; stdout is never touched.
- Callers should handle ``urllib.error.URLError`` for network failures.
"""

from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ecu.car import Car

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NHTSA_BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"

# Torque estimates (Nm) keyed by engine displacement (litres).
# Used when NHTSA does not provide HP/TQ data directly.
# Values are approximate NA peak-torque figures for typical production engines.
_DISPLACEMENT_TORQUE_NM: dict[float, float] = {
    0.8: 90.0,
    1.0: 115.0,
    1.2: 130.0,
    1.5: 150.0,
    1.6: 160.0,
    1.8: 175.0,
    2.0: 195.0,
    2.4: 225.0,
    2.5: 240.0,
    3.0: 285.0,
    3.5: 335.0,
    4.0: 385.0,
    4.6: 430.0,
    5.0: 475.0,
    5.7: 530.0,
    6.0: 570.0,
    6.2: 590.0,
    8.0: 720.0,
}

# Default weight (kg) when NHTSA does not provide curb weight.
_DEFAULT_WEIGHT_KG: float = 1450.0

# Redline estimates by aspiration and displacement.
_REDLINE_TABLE: list[tuple[str, float, int]] = [
    # (aspiration, max_displacement_l, redline_rpm)
    ("Turbo",        99.0, 6500),
    ("Supercharged", 99.0, 6200),
    ("NA",           1.4,  7500),
    ("NA",           2.0,  7200),
    ("NA",           3.0,  6800),
    ("NA",           4.5,  6200),
    ("NA",           99.0, 5800),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _estimate_torque_nm(displacement_l: float) -> float:
    """Linearly interpolate base torque (Nm) from engine displacement (L)."""
    if displacement_l <= 0 or not math.isfinite(displacement_l):
        return _DISPLACEMENT_TORQUE_NM[2.0]

    keys = sorted(_DISPLACEMENT_TORQUE_NM.keys())

    if displacement_l <= keys[0]:
        return _DISPLACEMENT_TORQUE_NM[keys[0]]
    if displacement_l >= keys[-1]:
        return _DISPLACEMENT_TORQUE_NM[keys[-1]]

    for i in range(1, len(keys)):
        k_lo = keys[i - 1]
        k_hi = keys[i]
        if displacement_l <= k_hi:
            t = (displacement_l - k_lo) / (k_hi - k_lo)
            tq_lo = _DISPLACEMENT_TORQUE_NM[k_lo]
            tq_hi = _DISPLACEMENT_TORQUE_NM[k_hi]
            return round(tq_lo + t * (tq_hi - tq_lo), 2)

    return _DISPLACEMENT_TORQUE_NM[keys[-1]]  # unreachable, but safe


def _estimate_redline(aspiration: str, displacement_l: float) -> int:
    """Estimate engine redline RPM from aspiration and displacement."""
    for asp, max_disp, redline in _REDLINE_TABLE:
        if aspiration == asp and displacement_l <= max_disp:
            return redline
    return 6000  # safe fallback


def _parse_aspiration(result: dict[str, Any]) -> str:
    """Derive aspiration string from NHTSA result fields."""
    turbo_raw = result.get("Turbo", "") or ""
    supercharger_raw = result.get("SuperchargerType", "") or ""

    turbo = turbo_raw.strip().upper()
    supercharger = supercharger_raw.strip().upper()

    if supercharger and supercharger not in ("", "NOT APPLICABLE", "NONE"):
        return "Supercharged"
    if turbo and turbo not in ("", "NOT APPLICABLE", "NONE"):
        return "Turbo"
    return "NA"


def _parse_drivetrain(result: dict[str, Any]) -> str:
    """Derive drivetrain string from NHTSA DriveType field."""
    drive_raw = (result.get("DriveType", "") or "").upper()
    if "AWD" in drive_raw or "4WD" in drive_raw or "4X4" in drive_raw:
        return "AWD"
    if "FWD" in drive_raw or "FRONT" in drive_raw:
        return "FWD"
    return "RWD"


def _parse_displacement(result: dict[str, Any]) -> float:
    """Parse engine displacement in litres from NHTSA result."""
    raw = result.get("DisplacementL", "") or ""
    try:
        val = float(raw)
        return val if math.isfinite(val) and val > 0 else 2.0
    except (ValueError, TypeError):
        return 2.0


def _fetch_json(url: str, timeout: float) -> Any:
    """Fetch a URL and return parsed JSON.  Logs to stderr only."""
    logger.info("NHTSA fetch: %s", url)
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "DynoMonsters/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_vehicle_by_vin(vin: str, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch raw NHTSA vPIC decode result for a VIN.

    Parameters
    ----------
    vin:
        17-character Vehicle Identification Number.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    dict
        The first result dict from the NHTSA ``DecodeVinValues`` endpoint.

    Raises
    ------
    ValueError
        If NHTSA returns no results.
    urllib.error.URLError
        On network failure.
    """
    url = (
        f"{NHTSA_BASE_URL}/DecodeVinValues/"
        f"{urllib.parse.quote(vin.strip())}?format=json"
    )
    data = _fetch_json(url, timeout)
    results = data.get("Results", [])
    if not results:
        raise ValueError(f"NHTSA returned no results for VIN: {vin!r}")
    return results[0]


def car_from_nhtsa_vin(vin: str, timeout: float = 10.0) -> Car:
    """Build a ``Car`` instance from NHTSA VIN decode data.

    Parameters
    ----------
    vin:
        17-character Vehicle Identification Number.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    Car
        A validated ``Car`` instance with base stats derived from NHTSA data.

    Raises
    ------
    ValueError
        If NHTSA returns no results or the resulting Car is invalid.
    urllib.error.URLError
        On network failure.
    """
    result = fetch_vehicle_by_vin(vin, timeout=timeout)

    make = (result.get("Make", "") or "Unknown").strip() or "Unknown"
    model = (result.get("Model", "") or "Unknown").strip() or "Unknown"

    year_raw = result.get("ModelYear", "") or ""
    year = int(year_raw) if year_raw.isdigit() else 2000

    displacement_l = _parse_displacement(result)
    aspiration = _parse_aspiration(result)
    drivetrain = _parse_drivetrain(result)

    base_torque_nm = _estimate_torque_nm(displacement_l)
    redline_rpm = _estimate_redline(aspiration, displacement_l)

    vehicle_id = (
        f"{make.lower()}-{model.lower()}-{year}"
        .replace(" ", "-")
        .replace("/", "-")
    )

    car = Car(
        vehicle_id=vehicle_id,
        make=make,
        model=model,
        year=year,
        base_torque_nm=base_torque_nm,
        weight_kg=_DEFAULT_WEIGHT_KG,
        redline_rpm=redline_rpm,
        aspiration=aspiration,
        drivetrain=drivetrain,
    )

    errors = car.validate()
    if errors:
        raise ValueError(f"Car built from NHTSA data failed validation: {errors}")

    logger.info(
        "Built Car from VIN %s: %s %s %d, %.0f Nm, %d RPM redline, %s",
        vin,
        make,
        model,
        year,
        base_torque_nm,
        redline_rpm,
        aspiration,
    )
    return car


def fetch_makes(timeout: float = 10.0) -> list[dict[str, Any]]:
    """Return all vehicle makes from the NHTSA vPIC API.

    Parameters
    ----------
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    list[dict]
        Each dict has at least ``"Make_ID"`` and ``"Make_Name"`` keys.
    """
    url = f"{NHTSA_BASE_URL}/getallmakes?format=json"
    data = _fetch_json(url, timeout)
    return data.get("Results", [])


def fetch_models_for_make(make: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Return all models for a given make from the NHTSA vPIC API.

    Parameters
    ----------
    make:
        Manufacturer name (e.g. ``"Toyota"``).
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    list[dict]
        Each dict has at least ``"Model_ID"`` and ``"Model_Name"`` keys.
    """
    url = (
        f"{NHTSA_BASE_URL}/getmodelsformake/"
        f"{urllib.parse.quote(make.strip())}?format=json"
    )
    data = _fetch_json(url, timeout)
    return data.get("Results", [])
