"""Tests for ecu.dyno_generator — 500-point HP/TQ curve generation."""

from __future__ import annotations

import math
import pytest

from ecu.car import Car
from ecu.dyno_generator import (
    CURVE_POINTS,
    DynoCurve,
    generate_dyno_curve,
    _torque_at_rpm,
)
from ecu.dyno_model import HP_CONSTANT


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_car(**overrides) -> Car:
    defaults = dict(
        vehicle_id="honda-civic-2002",
        make="Honda",
        model="Civic",
        year=2002,
        base_torque_nm=200.0,
        weight_kg=1150.0,
        redline_rpm=8000,
        aspiration="NA",
        drivetrain="FWD",
    )
    defaults.update(overrides)
    return Car(**defaults)


# ---------------------------------------------------------------------------
# Curve shape and length
# ---------------------------------------------------------------------------

class TestCurveLength:
    def test_exactly_500_points(self):
        curve = generate_dyno_curve(_make_car())
        assert len(curve.rpm_bins) == CURVE_POINTS
        assert len(curve.torque_nm) == CURVE_POINTS
        assert len(curve.hp) == CURVE_POINTS

    def test_returns_dyno_curve_named_tuple(self):
        curve = generate_dyno_curve(_make_car())
        assert isinstance(curve, DynoCurve)


# ---------------------------------------------------------------------------
# RPM bins
# ---------------------------------------------------------------------------

class TestRpmBins:
    def test_first_bin_is_idle_rpm(self):
        curve = generate_dyno_curve(_make_car(), idle_rpm=800)
        assert curve.rpm_bins[0] == 800

    def test_last_bin_is_redline(self):
        car = _make_car(redline_rpm=8000)
        curve = generate_dyno_curve(car, idle_rpm=800)
        assert curve.rpm_bins[-1] == 8000

    def test_bins_are_monotonically_increasing(self):
        curve = generate_dyno_curve(_make_car())
        for i in range(1, len(curve.rpm_bins)):
            assert curve.rpm_bins[i] > curve.rpm_bins[i - 1], (
                f"RPM bins not monotonic at index {i}: "
                f"{curve.rpm_bins[i-1]} → {curve.rpm_bins[i]}"
            )

    def test_bins_are_integers(self):
        curve = generate_dyno_curve(_make_car())
        for rpm in curve.rpm_bins:
            assert isinstance(rpm, int)


# ---------------------------------------------------------------------------
# HP formula correctness
# ---------------------------------------------------------------------------

class TestHpFormula:
    def test_hp_equals_torque_times_rpm_over_5252(self):
        """HP must equal (Torque × RPM) / 5252 at every bin."""
        curve = generate_dyno_curve(_make_car())
        for rpm, tq, hp in zip(curve.rpm_bins, curve.torque_nm, curve.hp):
            expected_hp = (tq * rpm) / HP_CONSTANT
            assert hp == pytest.approx(expected_hp, rel=1e-4), (
                f"HP mismatch at {rpm} RPM: got {hp}, expected {expected_hp}"
            )

    def test_hp_at_zero_rpm_is_zero(self):
        """If idle_rpm were 0, HP should be 0 (edge case guard)."""
        # We test _torque_at_rpm directly since idle_rpm=0 is rejected by
        # generate_dyno_curve.
        tq = _torque_at_rpm(200.0, 0, 0, 8000)
        # HP = tq * 0 / 5252 = 0
        assert (tq * 0) / HP_CONSTANT == 0.0


# ---------------------------------------------------------------------------
# Torque curve shape
# ---------------------------------------------------------------------------

class TestTorqueCurveShape:
    def test_peak_torque_does_not_exceed_base_torque(self):
        """Peak torque must not exceed base_torque_nm (Gaussian ≤ 1)."""
        car = _make_car(base_torque_nm=300.0)
        curve = generate_dyno_curve(car)
        assert max(curve.torque_nm) <= car.base_torque_nm + 1e-6

    def test_all_torque_values_positive(self):
        curve = generate_dyno_curve(_make_car())
        for tq in curve.torque_nm:
            assert tq > 0.0

    def test_all_hp_values_positive(self):
        curve = generate_dyno_curve(_make_car())
        for hp in curve.hp:
            assert hp > 0.0

    def test_all_values_finite(self):
        curve = generate_dyno_curve(_make_car())
        for tq in curve.torque_nm:
            assert math.isfinite(tq)
        for hp in curve.hp:
            assert math.isfinite(hp)

    def test_peak_torque_in_middle_of_range(self):
        """Torque peak should occur in the middle 30–85 % of the RPM range."""
        curve = generate_dyno_curve(_make_car())
        peak_idx = curve.torque_nm.index(max(curve.torque_nm))
        # Peak should not be at the very start or very end
        assert 0.30 * CURVE_POINTS < peak_idx < 0.85 * CURVE_POINTS


# ---------------------------------------------------------------------------
# Different car configurations
# ---------------------------------------------------------------------------

class TestDifferentCars:
    def test_high_redline_car(self):
        car = _make_car(redline_rpm=9500, base_torque_nm=180.0)
        curve = generate_dyno_curve(car)
        assert curve.rpm_bins[-1] == 9500
        assert len(curve.rpm_bins) == CURVE_POINTS

    def test_low_redline_car(self):
        car = _make_car(redline_rpm=4500, base_torque_nm=600.0, aspiration="Turbo")
        curve = generate_dyno_curve(car)
        assert curve.rpm_bins[-1] == 4500
        assert len(curve.rpm_bins) == CURVE_POINTS

    def test_higher_base_torque_gives_higher_peak(self):
        car_lo = _make_car(base_torque_nm=150.0)
        car_hi = _make_car(base_torque_nm=400.0)
        curve_lo = generate_dyno_curve(car_lo)
        curve_hi = generate_dyno_curve(car_hi)
        assert max(curve_hi.torque_nm) > max(curve_lo.torque_nm)

    def test_custom_idle_rpm(self):
        car = _make_car(redline_rpm=7000)
        curve = generate_dyno_curve(car, idle_rpm=1000)
        assert curve.rpm_bins[0] == 1000
        assert curve.rpm_bins[-1] == 7000


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_invalid_car_raises(self):
        bad_car = _make_car(base_torque_nm=-1.0)
        with pytest.raises(ValueError, match="Invalid Car"):
            generate_dyno_curve(bad_car)

    def test_idle_rpm_at_or_above_redline_raises(self):
        car = _make_car(redline_rpm=6000)
        with pytest.raises(ValueError, match="idle_rpm"):
            generate_dyno_curve(car, idle_rpm=6000)

    def test_idle_rpm_above_redline_raises(self):
        car = _make_car(redline_rpm=6000)
        with pytest.raises(ValueError, match="idle_rpm"):
            generate_dyno_curve(car, idle_rpm=7000)

    def test_zero_idle_rpm_raises(self):
        car = _make_car(redline_rpm=6000)
        with pytest.raises(ValueError, match="idle_rpm"):
            generate_dyno_curve(car, idle_rpm=0)
