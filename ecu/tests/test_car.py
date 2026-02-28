"""Tests for ecu.car — Car dataclass."""

from __future__ import annotations

import math
import pytest

from ecu.car import Car, VALID_ASPIRATIONS, VALID_DRIVETRAINS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _valid_car(**overrides) -> Car:
    """Return a valid Car with optional field overrides."""
    defaults = dict(
        vehicle_id="toyota-supra-1998",
        make="Toyota",
        model="Supra",
        year=1998,
        base_torque_nm=451.0,
        weight_kg=1560.0,
        redline_rpm=6800,
        aspiration="Turbo",
        drivetrain="RWD",
    )
    defaults.update(overrides)
    return Car(**defaults)


# ---------------------------------------------------------------------------
# Construction and basic access
# ---------------------------------------------------------------------------

class TestCarConstruction:
    def test_valid_car_is_valid(self):
        car = _valid_car()
        assert car.is_valid()
        assert car.validate() == []

    def test_fields_stored_correctly(self):
        car = _valid_car()
        assert car.vehicle_id == "toyota-supra-1998"
        assert car.make == "Toyota"
        assert car.model == "Supra"
        assert car.year == 1998
        assert car.base_torque_nm == pytest.approx(451.0)
        assert car.weight_kg == pytest.approx(1560.0)
        assert car.redline_rpm == 6800
        assert car.aspiration == "Turbo"
        assert car.drivetrain == "RWD"

    def test_default_aspiration_is_na(self):
        car = Car(
            vehicle_id="test",
            make="Test",
            model="Car",
            year=2000,
            base_torque_nm=200.0,
            weight_kg=1200.0,
            redline_rpm=6000,
        )
        assert car.aspiration == "NA"
        assert car.drivetrain == "RWD"


# ---------------------------------------------------------------------------
# Validation — base_torque_nm
# ---------------------------------------------------------------------------

class TestValidateBaseTorque:
    def test_zero_torque_invalid(self):
        errors = _valid_car(base_torque_nm=0.0).validate()
        assert any("base_torque_nm" in e for e in errors)

    def test_negative_torque_invalid(self):
        errors = _valid_car(base_torque_nm=-10.0).validate()
        assert any("base_torque_nm" in e for e in errors)

    def test_nan_torque_invalid(self):
        errors = _valid_car(base_torque_nm=float("nan")).validate()
        assert any("base_torque_nm" in e for e in errors)

    def test_inf_torque_invalid(self):
        errors = _valid_car(base_torque_nm=float("inf")).validate()
        assert any("base_torque_nm" in e for e in errors)

    def test_positive_torque_valid(self):
        assert _valid_car(base_torque_nm=0.001).is_valid()


# ---------------------------------------------------------------------------
# Validation — weight_kg
# ---------------------------------------------------------------------------

class TestValidateWeight:
    def test_zero_weight_invalid(self):
        errors = _valid_car(weight_kg=0.0).validate()
        assert any("weight_kg" in e for e in errors)

    def test_negative_weight_invalid(self):
        errors = _valid_car(weight_kg=-500.0).validate()
        assert any("weight_kg" in e for e in errors)

    def test_nan_weight_invalid(self):
        errors = _valid_car(weight_kg=float("nan")).validate()
        assert any("weight_kg" in e for e in errors)

    def test_positive_weight_valid(self):
        assert _valid_car(weight_kg=500.0).is_valid()


# ---------------------------------------------------------------------------
# Validation — redline_rpm
# ---------------------------------------------------------------------------

class TestValidateRedline:
    def test_zero_redline_invalid(self):
        errors = _valid_car(redline_rpm=0).validate()
        assert any("redline_rpm" in e for e in errors)

    def test_negative_redline_invalid(self):
        errors = _valid_car(redline_rpm=-1000).validate()
        assert any("redline_rpm" in e for e in errors)

    def test_positive_redline_valid(self):
        assert _valid_car(redline_rpm=9000).is_valid()


# ---------------------------------------------------------------------------
# Validation — aspiration
# ---------------------------------------------------------------------------

class TestValidateAspiration:
    @pytest.mark.parametrize("asp", sorted(VALID_ASPIRATIONS))
    def test_valid_aspirations(self, asp):
        assert _valid_car(aspiration=asp).is_valid()

    def test_invalid_aspiration(self):
        errors = _valid_car(aspiration="Diesel").validate()
        assert any("aspiration" in e for e in errors)

    def test_empty_aspiration_invalid(self):
        errors = _valid_car(aspiration="").validate()
        assert any("aspiration" in e for e in errors)


# ---------------------------------------------------------------------------
# Validation — drivetrain
# ---------------------------------------------------------------------------

class TestValidateDrivetrain:
    @pytest.mark.parametrize("dt", sorted(VALID_DRIVETRAINS))
    def test_valid_drivetrains(self, dt):
        assert _valid_car(drivetrain=dt).is_valid()

    def test_invalid_drivetrain(self):
        errors = _valid_car(drivetrain="4WD").validate()
        assert any("drivetrain" in e for e in errors)


# ---------------------------------------------------------------------------
# Validation — year
# ---------------------------------------------------------------------------

class TestValidateYear:
    def test_year_too_early(self):
        errors = _valid_car(year=1800).validate()
        assert any("year" in e for e in errors)

    def test_year_too_late(self):
        errors = _valid_car(year=2200).validate()
        assert any("year" in e for e in errors)

    def test_valid_year(self):
        assert _valid_car(year=2024).is_valid()


# ---------------------------------------------------------------------------
# Serialisation round-trip
# ---------------------------------------------------------------------------

class TestSerialisationRoundTrip:
    def test_to_dict_contains_all_fields(self):
        car = _valid_car()
        d = car.to_dict()
        assert set(d.keys()) == {
            "vehicle_id", "make", "model", "year",
            "base_torque_nm", "weight_kg", "redline_rpm",
            "aspiration", "drivetrain",
        }

    def test_from_dict_round_trip(self):
        car = _valid_car()
        d = car.to_dict()
        restored = Car.from_dict(d)
        assert restored == car

    def test_from_dict_uses_defaults(self):
        d = {
            "vehicle_id": "test",
            "make": "Test",
            "model": "Car",
            "year": 2000,
            "base_torque_nm": 200.0,
            "weight_kg": 1200.0,
            "redline_rpm": 6000,
        }
        car = Car.from_dict(d)
        assert car.aspiration == "NA"
        assert car.drivetrain == "RWD"

    def test_from_dict_invalid_raises(self):
        d = {
            "vehicle_id": "bad",
            "make": "Bad",
            "model": "Car",
            "year": 2000,
            "base_torque_nm": -1.0,   # invalid
            "weight_kg": 1200.0,
            "redline_rpm": 6000,
        }
        with pytest.raises(ValueError, match="Invalid Car"):
            Car.from_dict(d)

    def test_from_dict_missing_key_raises(self):
        with pytest.raises(KeyError):
            Car.from_dict({"vehicle_id": "x"})

    def test_to_dict_values_are_json_safe(self):
        """All values must be JSON-serialisable primitives."""
        import json
        car = _valid_car()
        json.dumps(car.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# Multiple validation errors
# ---------------------------------------------------------------------------

class TestMultipleErrors:
    def test_multiple_invalid_fields_all_reported(self):
        car = Car(
            vehicle_id="",
            make="",
            model="",
            year=1800,
            base_torque_nm=-1.0,
            weight_kg=0.0,
            redline_rpm=-100,
            aspiration="Diesel",
            drivetrain="4WD",
        )
        errors = car.validate()
        assert len(errors) >= 7
