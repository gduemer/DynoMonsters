"""Tests for ecu.biome — biome modifier logic (altitude + temperature)."""

from __future__ import annotations

import math
import pytest

from ecu.biome import (
    SCALE_HEIGHT_M,
    STD_TEMP_C,
    apply_biome_modifier,
    biome_summary,
    compute_wear_multiplier,
    _air_density_ratio,
    _altitude_power_factor,
    _temperature_power_factor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BASELINE_TORQUE = [200.0, 220.0, 240.0, 235.0, 210.0]


# ---------------------------------------------------------------------------
# _air_density_ratio
# ---------------------------------------------------------------------------

class TestAirDensityRatio:
    def test_sea_level_is_one(self):
        assert _air_density_ratio(0.0) == pytest.approx(1.0)

    def test_positive_altitude_reduces_density(self):
        assert _air_density_ratio(1000.0) < 1.0

    def test_higher_altitude_lower_density(self):
        assert _air_density_ratio(3000.0) < _air_density_ratio(1000.0)

    def test_scale_height_gives_1_over_e(self):
        """At altitude = SCALE_HEIGHT_M, density ratio ≈ 1/e."""
        ratio = _air_density_ratio(SCALE_HEIGHT_M)
        assert ratio == pytest.approx(1.0 / math.e, rel=1e-6)

    def test_result_always_positive(self):
        for alt in [0, 500, 2000, 5000, 8848]:
            assert _air_density_ratio(alt) > 0.0


# ---------------------------------------------------------------------------
# _altitude_power_factor
# ---------------------------------------------------------------------------

class TestAltitudePowerFactor:
    def test_sea_level_all_aspirations_return_one(self):
        for asp in ("NA", "Turbo", "Supercharged"):
            assert _altitude_power_factor(0.0, asp) == pytest.approx(1.0)

    def test_na_loses_more_than_turbo_at_altitude(self):
        alt = 3000.0
        na_factor = _altitude_power_factor(alt, "NA")
        turbo_factor = _altitude_power_factor(alt, "Turbo")
        assert na_factor < turbo_factor

    def test_na_loses_more_than_supercharged_at_altitude(self):
        alt = 3000.0
        na_factor = _altitude_power_factor(alt, "NA")
        sc_factor = _altitude_power_factor(alt, "Supercharged")
        assert na_factor < sc_factor

    def test_turbo_loses_less_than_supercharged_at_altitude(self):
        """Turbo compensates 50 %, Supercharged 30 % → Turbo retains more."""
        alt = 3000.0
        turbo_factor = _altitude_power_factor(alt, "Turbo")
        sc_factor = _altitude_power_factor(alt, "Supercharged")
        assert turbo_factor > sc_factor

    def test_factor_never_below_minimum(self):
        from ecu.biome import _MIN_POWER_FACTOR
        for alt in [0, 5000, 10000, 50000]:
            for asp in ("NA", "Turbo", "Supercharged"):
                assert _altitude_power_factor(alt, asp) >= _MIN_POWER_FACTOR

    def test_unknown_aspiration_treated_as_na(self):
        """Unknown aspiration should use 0.0 compensation (most conservative)."""
        alt = 3000.0
        unknown = _altitude_power_factor(alt, "Diesel")
        na = _altitude_power_factor(alt, "NA")
        assert unknown == pytest.approx(na)


# ---------------------------------------------------------------------------
# _temperature_power_factor
# ---------------------------------------------------------------------------

class TestTemperaturePowerFactor:
    def test_standard_temp_returns_one(self):
        assert _temperature_power_factor(STD_TEMP_C) == pytest.approx(1.0)

    def test_below_standard_returns_one(self):
        assert _temperature_power_factor(STD_TEMP_C - 10.0) == pytest.approx(1.0)

    def test_above_standard_reduces_power(self):
        assert _temperature_power_factor(STD_TEMP_C + 10.0) < 1.0

    def test_higher_temp_lower_factor(self):
        assert _temperature_power_factor(50.0) < _temperature_power_factor(35.0)

    def test_factor_never_below_0_5(self):
        assert _temperature_power_factor(1000.0) >= 0.5

    def test_10_degrees_above_standard_loses_1_percent(self):
        """Each 10 °C above standard → 1 % power loss."""
        factor = _temperature_power_factor(STD_TEMP_C + 10.0)
        assert factor == pytest.approx(0.99, rel=1e-4)


# ---------------------------------------------------------------------------
# apply_biome_modifier — core behaviour
# ---------------------------------------------------------------------------

class TestApplyBiomeModifier:
    def test_sea_level_standard_temp_no_change(self):
        """At sea level and standard temp, torque must be unchanged."""
        result = apply_biome_modifier(_BASELINE_TORQUE, 0.0, STD_TEMP_C, "NA")
        for orig, mod in zip(_BASELINE_TORQUE, result):
            assert mod == pytest.approx(orig, rel=1e-4)

    def test_altitude_reduces_na_torque(self):
        result = apply_biome_modifier(_BASELINE_TORQUE, 3000.0, STD_TEMP_C, "NA")
        for orig, mod in zip(_BASELINE_TORQUE, result):
            assert mod < orig

    def test_altitude_reduces_turbo_torque_less_than_na(self):
        alt = 3000.0
        na_result = apply_biome_modifier(_BASELINE_TORQUE, alt, STD_TEMP_C, "NA")
        turbo_result = apply_biome_modifier(_BASELINE_TORQUE, alt, STD_TEMP_C, "Turbo")
        for na_tq, turbo_tq in zip(na_result, turbo_result):
            assert turbo_tq > na_tq

    def test_high_temp_reduces_torque(self):
        result = apply_biome_modifier(_BASELINE_TORQUE, 0.0, STD_TEMP_C + 30.0, "NA")
        for orig, mod in zip(_BASELINE_TORQUE, result):
            assert mod < orig

    def test_output_length_matches_input(self):
        result = apply_biome_modifier(_BASELINE_TORQUE, 1000.0, 30.0, "Turbo")
        assert len(result) == len(_BASELINE_TORQUE)

    def test_all_output_values_finite(self):
        result = apply_biome_modifier(_BASELINE_TORQUE, 2000.0, 35.0, "NA")
        for tq in result:
            assert math.isfinite(tq)

    def test_all_output_values_positive(self):
        result = apply_biome_modifier(_BASELINE_TORQUE, 5000.0, 50.0, "NA")
        for tq in result:
            assert tq > 0.0

    def test_supercharged_between_na_and_turbo(self):
        alt = 3000.0
        na = apply_biome_modifier(_BASELINE_TORQUE, alt, STD_TEMP_C, "NA")
        sc = apply_biome_modifier(_BASELINE_TORQUE, alt, STD_TEMP_C, "Supercharged")
        turbo = apply_biome_modifier(_BASELINE_TORQUE, alt, STD_TEMP_C, "Turbo")
        for na_tq, sc_tq, turbo_tq in zip(na, sc, turbo):
            assert na_tq < sc_tq < turbo_tq

    def test_combined_altitude_and_temp_effect(self):
        """Combined effect must be less than either effect alone."""
        alt = 2000.0
        hot_temp = STD_TEMP_C + 20.0
        baseline_only = apply_biome_modifier(_BASELINE_TORQUE, 0.0, STD_TEMP_C, "NA")
        combined = apply_biome_modifier(_BASELINE_TORQUE, alt, hot_temp, "NA")
        for base_tq, comb_tq in zip(baseline_only, combined):
            assert comb_tq < base_tq


# ---------------------------------------------------------------------------
# apply_biome_modifier — input validation
# ---------------------------------------------------------------------------

class TestApplyBiomeModifierValidation:
    def test_empty_torque_raises(self):
        with pytest.raises(ValueError, match="empty"):
            apply_biome_modifier([], 0.0, 25.0)

    def test_negative_altitude_raises(self):
        with pytest.raises(ValueError, match="altitude_m"):
            apply_biome_modifier(_BASELINE_TORQUE, -1.0, 25.0)

    def test_nan_altitude_raises(self):
        with pytest.raises(ValueError, match="altitude_m"):
            apply_biome_modifier(_BASELINE_TORQUE, float("nan"), 25.0)

    def test_inf_altitude_raises(self):
        with pytest.raises(ValueError, match="altitude_m"):
            apply_biome_modifier(_BASELINE_TORQUE, float("inf"), 25.0)

    def test_nan_temp_raises(self):
        with pytest.raises(ValueError, match="ambient_temp_c"):
            apply_biome_modifier(_BASELINE_TORQUE, 0.0, float("nan"))

    def test_nan_torque_value_raises(self):
        bad_torque = [200.0, float("nan"), 220.0]
        with pytest.raises(ValueError, match="Non-finite"):
            apply_biome_modifier(bad_torque, 0.0, 25.0)

    def test_inf_torque_value_raises(self):
        bad_torque = [200.0, float("inf"), 220.0]
        with pytest.raises(ValueError, match="Non-finite"):
            apply_biome_modifier(bad_torque, 0.0, 25.0)


# ---------------------------------------------------------------------------
# compute_wear_multiplier
# ---------------------------------------------------------------------------

class TestComputeWearMultiplier:
    def test_standard_temp_returns_one(self):
        assert compute_wear_multiplier(STD_TEMP_C) == pytest.approx(1.0)

    def test_below_standard_returns_one(self):
        assert compute_wear_multiplier(STD_TEMP_C - 20.0) == pytest.approx(1.0)

    def test_above_standard_increases_wear(self):
        assert compute_wear_multiplier(STD_TEMP_C + 10.0) > 1.0

    def test_10_degrees_above_adds_5_percent(self):
        """Each 10 °C above standard adds 5 % wear."""
        mult = compute_wear_multiplier(STD_TEMP_C + 10.0)
        assert mult == pytest.approx(1.05, rel=1e-4)

    def test_20_degrees_above_adds_10_percent(self):
        mult = compute_wear_multiplier(STD_TEMP_C + 20.0)
        assert mult == pytest.approx(1.10, rel=1e-4)

    def test_result_always_at_least_one(self):
        for temp in [-40.0, 0.0, 25.0, 50.0, 100.0]:
            assert compute_wear_multiplier(temp) >= 1.0

    def test_nan_raises(self):
        with pytest.raises(ValueError, match="finite"):
            compute_wear_multiplier(float("nan"))

    def test_inf_raises(self):
        with pytest.raises(ValueError, match="finite"):
            compute_wear_multiplier(float("inf"))


# ---------------------------------------------------------------------------
# biome_summary
# ---------------------------------------------------------------------------

class TestBiomeSummary:
    def test_returns_all_expected_keys(self):
        summary = biome_summary(0.0, STD_TEMP_C, "NA")
        expected_keys = {
            "air_density_ratio",
            "altitude_power_factor",
            "temperature_power_factor",
            "total_power_factor",
            "wear_multiplier",
        }
        assert set(summary.keys()) == expected_keys

    def test_sea_level_standard_temp_all_ones(self):
        summary = biome_summary(0.0, STD_TEMP_C, "NA")
        assert summary["air_density_ratio"] == pytest.approx(1.0)
        assert summary["altitude_power_factor"] == pytest.approx(1.0)
        assert summary["temperature_power_factor"] == pytest.approx(1.0)
        assert summary["total_power_factor"] == pytest.approx(1.0)
        assert summary["wear_multiplier"] == pytest.approx(1.0)

    def test_all_values_finite(self):
        summary = biome_summary(2000.0, 35.0, "Turbo")
        for v in summary.values():
            assert math.isfinite(v)

    def test_total_factor_equals_alt_times_temp(self):
        summary = biome_summary(1500.0, 30.0, "NA")
        expected = summary["altitude_power_factor"] * summary["temperature_power_factor"]
        assert summary["total_power_factor"] == pytest.approx(expected, rel=1e-5)

    def test_invalid_altitude_raises(self):
        with pytest.raises(ValueError, match="altitude_m"):
            biome_summary(-100.0, 25.0)

    def test_invalid_temp_raises(self):
        with pytest.raises(ValueError, match="ambient_temp_c"):
            biome_summary(0.0, float("nan"))
