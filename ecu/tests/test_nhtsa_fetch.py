"""Tests for ecu.nhtsa_fetch — NHTSA API fetch and Car construction.

Network calls are mocked via unittest.mock so tests run offline.
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from ecu.car import Car
from ecu.nhtsa_fetch import (
    NHTSA_BASE_URL,
    _estimate_torque_nm,
    _parse_aspiration,
    _parse_drivetrain,
    _parse_displacement,
    car_from_nhtsa_vin,
    fetch_vehicle_by_vin,
    fetch_makes,
    fetch_models_for_make,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_urlopen(payload: dict):
    """Return a context-manager mock that yields a response with JSON payload."""
    raw = json.dumps(payload).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _nhtsa_vin_response(overrides: dict | None = None) -> dict:
    """Build a minimal NHTSA DecodeVinValues response."""
    result = {
        "Make": "Toyota",
        "Model": "Supra",
        "ModelYear": "1998",
        "DisplacementL": "3.0",
        "Turbo": "Yes",
        "SuperchargerType": "",
        "DriveType": "RWD",
    }
    if overrides:
        result.update(overrides)
    return {"Results": [result]}


# ---------------------------------------------------------------------------
# _estimate_torque_nm
# ---------------------------------------------------------------------------

class TestEstimateTorqueNm:
    def test_known_2_litre(self):
        tq = _estimate_torque_nm(2.0)
        assert tq == pytest.approx(195.0, rel=1e-3)

    def test_known_3_litre(self):
        tq = _estimate_torque_nm(3.0)
        assert tq == pytest.approx(285.0, rel=1e-3)

    def test_interpolation_between_2_and_2_4(self):
        tq = _estimate_torque_nm(2.2)
        assert 195.0 < tq < 225.0

    def test_below_minimum_returns_smallest_entry(self):
        tq = _estimate_torque_nm(0.1)
        assert tq > 0.0

    def test_above_maximum_returns_largest_entry(self):
        tq = _estimate_torque_nm(20.0)
        assert tq > 0.0

    def test_zero_displacement_returns_default(self):
        tq = _estimate_torque_nm(0.0)
        assert tq > 0.0

    def test_negative_displacement_returns_default(self):
        tq = _estimate_torque_nm(-1.0)
        assert tq > 0.0

    def test_result_is_positive_finite(self):
        import math
        for disp in [0.8, 1.5, 2.0, 3.5, 5.0, 8.0]:
            tq = _estimate_torque_nm(disp)
            assert math.isfinite(tq) and tq > 0


# ---------------------------------------------------------------------------
# _parse_aspiration
# ---------------------------------------------------------------------------

class TestParseAspiration:
    def test_turbo_yes(self):
        assert _parse_aspiration({"Turbo": "Yes", "SuperchargerType": ""}) == "Turbo"

    def test_supercharged(self):
        assert _parse_aspiration({"Turbo": "", "SuperchargerType": "Roots"}) == "Supercharged"

    def test_supercharged_takes_priority_over_turbo(self):
        # Supercharged check runs first
        result = _parse_aspiration({"Turbo": "Yes", "SuperchargerType": "Roots"})
        assert result == "Supercharged"

    def test_na_when_both_empty(self):
        assert _parse_aspiration({"Turbo": "", "SuperchargerType": ""}) == "NA"

    def test_na_when_not_applicable(self):
        assert _parse_aspiration({"Turbo": "Not Applicable", "SuperchargerType": "None"}) == "NA"

    def test_missing_keys_returns_na(self):
        assert _parse_aspiration({}) == "NA"


# ---------------------------------------------------------------------------
# _parse_drivetrain
# ---------------------------------------------------------------------------

class TestParseDrivetrain:
    def test_awd(self):
        assert _parse_drivetrain({"DriveType": "AWD"}) == "AWD"

    def test_4wd(self):
        assert _parse_drivetrain({"DriveType": "4WD"}) == "AWD"

    def test_fwd(self):
        assert _parse_drivetrain({"DriveType": "FWD"}) == "FWD"

    def test_front_wheel_drive(self):
        assert _parse_drivetrain({"DriveType": "Front-Wheel Drive"}) == "FWD"

    def test_rwd_default(self):
        assert _parse_drivetrain({"DriveType": "RWD"}) == "RWD"

    def test_empty_defaults_to_rwd(self):
        assert _parse_drivetrain({"DriveType": ""}) == "RWD"

    def test_missing_key_defaults_to_rwd(self):
        assert _parse_drivetrain({}) == "RWD"


# ---------------------------------------------------------------------------
# _parse_displacement
# ---------------------------------------------------------------------------

class TestParseDisplacement:
    def test_valid_float_string(self):
        assert _parse_displacement({"DisplacementL": "3.0"}) == pytest.approx(3.0)

    def test_integer_string(self):
        assert _parse_displacement({"DisplacementL": "2"}) == pytest.approx(2.0)

    def test_empty_string_returns_default(self):
        assert _parse_displacement({"DisplacementL": ""}) == pytest.approx(2.0)

    def test_none_returns_default(self):
        assert _parse_displacement({"DisplacementL": None}) == pytest.approx(2.0)

    def test_non_numeric_returns_default(self):
        assert _parse_displacement({"DisplacementL": "N/A"}) == pytest.approx(2.0)

    def test_missing_key_returns_default(self):
        assert _parse_displacement({}) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# fetch_vehicle_by_vin (mocked)
# ---------------------------------------------------------------------------

class TestFetchVehicleByVin:
    def test_returns_first_result(self):
        payload = _nhtsa_vin_response()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            result = fetch_vehicle_by_vin("1HGBH41JXMN109186")
        assert result["Make"] == "Toyota"
        assert result["Model"] == "Supra"

    def test_empty_results_raises(self):
        payload = {"Results": []}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            with pytest.raises(ValueError, match="no results"):
                fetch_vehicle_by_vin("BADVIN00000000000")

    def test_url_contains_vin(self):
        payload = _nhtsa_vin_response()
        vin = "1HGBH41JXMN109186"
        captured_url = []

        def fake_urlopen(req, timeout):
            captured_url.append(req.full_url)
            return _mock_urlopen(payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fetch_vehicle_by_vin(vin)

        assert vin in captured_url[0]
        assert NHTSA_BASE_URL in captured_url[0]


# ---------------------------------------------------------------------------
# car_from_nhtsa_vin (mocked)
# ---------------------------------------------------------------------------

class TestCarFromNhtsaVin:
    def test_returns_valid_car(self):
        payload = _nhtsa_vin_response()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert isinstance(car, Car)
        assert car.is_valid()

    def test_make_and_model_populated(self):
        payload = _nhtsa_vin_response({"Make": "Honda", "Model": "Civic"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.make == "Honda"
        assert car.model == "Civic"

    def test_year_parsed(self):
        payload = _nhtsa_vin_response({"ModelYear": "2005"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.year == 2005

    def test_turbo_aspiration(self):
        payload = _nhtsa_vin_response({"Turbo": "Yes", "SuperchargerType": ""})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.aspiration == "Turbo"

    def test_na_aspiration(self):
        payload = _nhtsa_vin_response({"Turbo": "", "SuperchargerType": ""})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.aspiration == "NA"

    def test_awd_drivetrain(self):
        payload = _nhtsa_vin_response({"DriveType": "AWD"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.drivetrain == "AWD"

    def test_base_torque_positive(self):
        payload = _nhtsa_vin_response({"DisplacementL": "2.0"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.base_torque_nm > 0.0

    def test_redline_positive(self):
        payload = _nhtsa_vin_response()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.redline_rpm > 0

    def test_invalid_year_defaults_to_2000(self):
        payload = _nhtsa_vin_response({"ModelYear": "UNKNOWN"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert car.year == 2000

    def test_vehicle_id_contains_make_model_year(self):
        payload = _nhtsa_vin_response({"Make": "Ford", "Model": "Mustang", "ModelYear": "2020"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            car = car_from_nhtsa_vin("1HGBH41JXMN109186")
        assert "ford" in car.vehicle_id
        assert "mustang" in car.vehicle_id
        assert "2020" in car.vehicle_id


# ---------------------------------------------------------------------------
# fetch_makes (mocked)
# ---------------------------------------------------------------------------

class TestFetchMakes:
    def test_returns_list(self):
        payload = {"Results": [{"Make_ID": 1, "Make_Name": "Toyota"}]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            makes = fetch_makes()
        assert isinstance(makes, list)
        assert makes[0]["Make_Name"] == "Toyota"

    def test_empty_results_returns_empty_list(self):
        payload = {"Results": []}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            makes = fetch_makes()
        assert makes == []


# ---------------------------------------------------------------------------
# fetch_models_for_make (mocked)
# ---------------------------------------------------------------------------

class TestFetchModelsForMake:
    def test_returns_list(self):
        payload = {"Results": [{"Model_ID": 1, "Model_Name": "Supra"}]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            models = fetch_models_for_make("Toyota")
        assert isinstance(models, list)
        assert models[0]["Model_Name"] == "Supra"

    def test_make_encoded_in_url(self):
        payload = {"Results": []}
        captured = []

        def fake_urlopen(req, timeout):
            captured.append(req.full_url)
            return _mock_urlopen(payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fetch_models_for_make("Toyota")

        assert "Toyota" in captured[0]
