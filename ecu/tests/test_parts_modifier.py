"""Tests for ecu.parts_modifier — intake upgrade physics model.

Physics under test:
    gain_ratio(rpm) = BASE_GAIN × level_scale × aspiration_scale
                      × condition × (rpm / redline_rpm)²

Key properties verified:
  - Gain is zero at rpm=0 (no airflow → no restriction loss)
  - Gain grows quadratically with RPM
  - Gain peaks at redline
  - NA gains more than Turbo, Turbo more than Supercharged
  - condition=0 → no gain; condition=0.5 → half gain
  - Higher level → higher gain
  - Output length always matches input
  - All output values are finite and ≥ baseline
"""

from __future__ import annotations

import math
import pytest

from ecu.parts_modifier import (
    INTAKE_BASE_GAIN,
    INTAKE_PROFILE,
    PART_PROFILES,
    SUPPORTED_CATEGORIES,
    PartProfile,
    apply_part_effects,
    intake_gain_curve,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_REDLINE = 7000
_IDLE = 800
_N = 7
_RPM_BINS = [
    int(_IDLE + i * (_REDLINE - _IDLE) / (_N - 1)) for i in range(_N)
]
_BASELINE_TQ = [180.0, 210.0, 240.0, 250.0, 245.0, 225.0, 190.0]

_INTAKE_PART = {"category": "intake", "level": 1, "condition": 1.0}


def _apply_intake(**overrides):
    part = dict(_INTAKE_PART)
    part.update(overrides)
    return apply_part_effects(
        _BASELINE_TQ, _RPM_BINS, _REDLINE, [part], aspiration="NA"
    )


# ---------------------------------------------------------------------------
# PartProfile.gain_at_rpm — physics unit tests
# ---------------------------------------------------------------------------

class TestGainAtRpm:
    def test_zero_rpm_gives_zero_gain(self):
        """At rpm=0, RPM² = 0 → no restriction loss → no gain."""
        gain = INTAKE_PROFILE.gain_at_rpm(0, _REDLINE, "NA", 1, 1.0)
        assert gain == pytest.approx(0.0)

    def test_gain_at_redline_equals_base_gain_na_level1(self):
        """At redline, NA, Level 1, condition=1.0 → gain = BASE_GAIN exactly."""
        gain = INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", 1, 1.0)
        assert gain == pytest.approx(INTAKE_BASE_GAIN, rel=1e-6)

    def test_gain_grows_quadratically_with_rpm(self):
        """Doubling RPM should quadruple the gain (RPM² physics)."""
        gain_half = INTAKE_PROFILE.gain_at_rpm(_REDLINE // 2, _REDLINE, "NA", 1, 1.0)
        gain_full = INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", 1, 1.0)
        assert gain_full == pytest.approx(4.0 * gain_half, rel=1e-6)

    def test_gain_at_quarter_redline(self):
        """At 25% of redline, gain = BASE_GAIN × 0.25² = BASE_GAIN × 0.0625."""
        gain = INTAKE_PROFILE.gain_at_rpm(_REDLINE // 4, _REDLINE, "NA", 1, 1.0)
        assert gain == pytest.approx(INTAKE_BASE_GAIN * 0.0625, rel=1e-5)

    def test_na_gains_more_than_turbo(self):
        rpm = int(_REDLINE * 0.8)
        na = INTAKE_PROFILE.gain_at_rpm(rpm, _REDLINE, "NA", 1, 1.0)
        turbo = INTAKE_PROFILE.gain_at_rpm(rpm, _REDLINE, "Turbo", 1, 1.0)
        assert na > turbo

    def test_turbo_gains_more_than_supercharged(self):
        rpm = int(_REDLINE * 0.8)
        turbo = INTAKE_PROFILE.gain_at_rpm(rpm, _REDLINE, "Turbo", 1, 1.0)
        sc = INTAKE_PROFILE.gain_at_rpm(rpm, _REDLINE, "Supercharged", 1, 1.0)
        assert turbo > sc

    def test_condition_zero_gives_zero_gain(self):
        gain = INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", 1, 0.0)
        assert gain == pytest.approx(0.0)

    def test_condition_half_gives_half_gain(self):
        full = INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", 1, 1.0)
        half = INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", 1, 0.5)
        assert half == pytest.approx(full * 0.5, rel=1e-6)

    def test_higher_level_gives_higher_gain(self):
        gains = [
            INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", lvl, 1.0)
            for lvl in range(1, 6)
        ]
        for i in range(1, len(gains)):
            assert gains[i] > gains[i - 1]

    def test_level_5_gain_is_2_3x_level_1(self):
        """Level 5 scale = 2.30 × Level 1 scale."""
        g1 = INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", 1, 1.0)
        g5 = INTAKE_PROFILE.gain_at_rpm(_REDLINE, _REDLINE, "NA", 5, 1.0)
        assert g5 == pytest.approx(g1 * 2.30, rel=1e-5)

    def test_zero_redline_returns_zero(self):
        """Guard against division by zero."""
        gain = INTAKE_PROFILE.gain_at_rpm(3000, 0, "NA", 1, 1.0)
        assert gain == pytest.approx(0.0)

    def test_gain_always_non_negative(self):
        for rpm in [0, 500, 1000, 3500, 7000]:
            for asp in ("NA", "Turbo", "Supercharged"):
                for lvl in (1, 3, 5):
                    gain = INTAKE_PROFILE.gain_at_rpm(rpm, _REDLINE, asp, lvl, 1.0)
                    assert gain >= 0.0


# ---------------------------------------------------------------------------
# apply_part_effects — torque curve modification
# ---------------------------------------------------------------------------

class TestApplyPartEffects:
    def test_output_length_matches_input(self):
        result = _apply_intake()
        assert len(result) == len(_BASELINE_TQ)

    def test_intake_increases_all_torque_values(self):
        """Every bin should be ≥ baseline (gain ≥ 0 everywhere)."""
        result = _apply_intake()
        for orig, mod in zip(_BASELINE_TQ, result):
            assert mod >= orig - 1e-9

    def test_gain_is_larger_at_high_rpm_than_low_rpm(self):
        """Upper RPM bins must gain more than lower RPM bins (RPM² physics)."""
        result = _apply_intake()
        low_gain = result[0] - _BASELINE_TQ[0]   # lowest RPM bin
        high_gain = result[-1] - _BASELINE_TQ[-1]  # highest RPM bin
        assert high_gain > low_gain

    def test_gain_at_redline_approx_4_percent_na_level1(self):
        """At redline, NA, Level 1, new: gain ≈ 4% of baseline torque."""
        result = _apply_intake()
        last_orig = _BASELINE_TQ[-1]
        last_mod = result[-1]
        gain_ratio = (last_mod - last_orig) / last_orig
        assert gain_ratio == pytest.approx(INTAKE_BASE_GAIN, rel=0.01)

    def test_condition_zero_no_change(self):
        result = _apply_intake(condition=0.0)
        for orig, mod in zip(_BASELINE_TQ, result):
            assert mod == pytest.approx(orig)

    def test_condition_half_gives_half_gain(self):
        full = _apply_intake(condition=1.0)
        half = _apply_intake(condition=0.5)
        for orig, f, h in zip(_BASELINE_TQ, full, half):
            full_gain = f - orig
            half_gain = h - orig
            assert half_gain == pytest.approx(full_gain * 0.5, abs=1e-4)

    def test_na_gains_more_than_turbo_at_every_bin(self):
        na = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, [_INTAKE_PART], aspiration="NA"
        )
        turbo = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, [_INTAKE_PART], aspiration="Turbo"
        )
        for na_tq, turbo_tq in zip(na, turbo):
            assert na_tq >= turbo_tq - 1e-9

    def test_turbo_gains_more_than_supercharged(self):
        turbo = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, [_INTAKE_PART], aspiration="Turbo"
        )
        sc = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, [_INTAKE_PART], aspiration="Supercharged"
        )
        for t_tq, sc_tq in zip(turbo, sc):
            assert t_tq >= sc_tq - 1e-9

    def test_level_5_gains_more_than_level_1(self):
        l1 = _apply_intake(level=1)
        l5 = _apply_intake(level=5)
        for orig, t1, t5 in zip(_BASELINE_TQ, l1, l5):
            assert t5 >= t1 - 1e-9

    def test_empty_parts_list_returns_unchanged_curve(self):
        result = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, [], aspiration="NA"
        )
        for orig, mod in zip(_BASELINE_TQ, result):
            assert mod == pytest.approx(orig)

    def test_unsupported_category_skipped(self):
        """Unknown part categories must not change the curve."""
        parts = [{"category": "nitrous", "level": 5, "condition": 1.0}]
        result = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, parts, aspiration="NA"
        )
        for orig, mod in zip(_BASELINE_TQ, result):
            assert mod == pytest.approx(orig)

    def test_all_output_values_finite(self):
        result = _apply_intake()
        for tq in result:
            assert math.isfinite(tq)

    def test_all_output_values_positive(self):
        result = _apply_intake()
        for tq in result:
            assert tq > 0.0

    def test_two_intakes_stack_additively(self):
        """Two Level-1 intakes should give approximately 2× the gain of one.

        Tolerance is 1e-3 Nm (1 millinewton-metre) to absorb the ±0.0001 Nm
        rounding introduced by round(..., 4) in apply_part_effects.  The
        stacking logic is mathematically exact; only the final rounding step
        can shift the result by at most half an ULP at 4 decimal places.
        """
        one = _apply_intake(level=1)
        two_parts = [
            {"category": "intake", "level": 1, "condition": 1.0},
            {"category": "intake", "level": 1, "condition": 1.0},
        ]
        two = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, two_parts, aspiration="NA"
        )
        for orig, o, t in zip(_BASELINE_TQ, one, two):
            one_gain = o - orig
            two_gain = t - orig
            assert two_gain == pytest.approx(2.0 * one_gain, abs=1e-3)

    def test_non_finite_condition_part_is_skipped(self):
        """A part with NaN condition must be skipped, not crash."""
        parts = [{"category": "intake", "level": 1, "condition": float("nan")}]
        result = apply_part_effects(
            _BASELINE_TQ, _RPM_BINS, _REDLINE, parts, aspiration="NA"
        )
        # NaN condition → skipped → curve unchanged
        for orig, mod in zip(_BASELINE_TQ, result):
            assert mod == pytest.approx(orig)


# ---------------------------------------------------------------------------
# apply_part_effects — input validation
# ---------------------------------------------------------------------------

class TestApplyPartEffectsValidation:
    def test_empty_torque_raises(self):
        with pytest.raises(ValueError, match="empty"):
            apply_part_effects([], [], _REDLINE, [], "NA")

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="mismatch"):
            apply_part_effects([200.0, 210.0], [1000], _REDLINE, [], "NA")

    def test_zero_redline_raises(self):
        with pytest.raises(ValueError, match="redline_rpm"):
            apply_part_effects(_BASELINE_TQ, _RPM_BINS, 0, [], "NA")

    def test_negative_redline_raises(self):
        with pytest.raises(ValueError, match="redline_rpm"):
            apply_part_effects(_BASELINE_TQ, _RPM_BINS, -1000, [], "NA")

    def test_nan_torque_raises(self):
        bad = list(_BASELINE_TQ)
        bad[2] = float("nan")
        with pytest.raises(ValueError, match="Non-finite"):
            apply_part_effects(bad, _RPM_BINS, _REDLINE, [], "NA")

    def test_inf_torque_raises(self):
        bad = list(_BASELINE_TQ)
        bad[0] = float("inf")
        with pytest.raises(ValueError, match="Non-finite"):
            apply_part_effects(bad, _RPM_BINS, _REDLINE, [], "NA")


# ---------------------------------------------------------------------------
# intake_gain_curve — convenience function
# ---------------------------------------------------------------------------

class TestIntakeGainCurve:
    def test_returns_correct_length(self):
        gains = intake_gain_curve(_RPM_BINS, _REDLINE)
        assert len(gains) == len(_RPM_BINS)

    def test_first_bin_near_zero(self):
        """Lowest RPM bin should have very small gain."""
        gains = intake_gain_curve(_RPM_BINS, _REDLINE)
        assert gains[0] < 0.005  # less than 0.5%

    def test_last_bin_equals_base_gain_na_level1(self):
        """At redline, NA, Level 1, condition=1.0 → gain = BASE_GAIN."""
        gains = intake_gain_curve(_RPM_BINS, _REDLINE, "NA", 1, 1.0)
        assert gains[-1] == pytest.approx(INTAKE_BASE_GAIN, rel=1e-5)

    def test_gains_are_monotonically_increasing(self):
        """Gain must increase monotonically (RPM² is strictly increasing)."""
        gains = intake_gain_curve(_RPM_BINS, _REDLINE)
        for i in range(1, len(gains)):
            assert gains[i] >= gains[i - 1]

    def test_all_gains_non_negative(self):
        gains = intake_gain_curve(_RPM_BINS, _REDLINE, "Turbo", 3, 0.7)
        for g in gains:
            assert g >= 0.0

    def test_condition_zero_all_zeros(self):
        gains = intake_gain_curve(_RPM_BINS, _REDLINE, condition=0.0)
        for g in gains:
            assert g == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# PART_PROFILES registry
# ---------------------------------------------------------------------------

class TestPartProfilesRegistry:
    def test_intake_in_registry(self):
        assert "intake" in PART_PROFILES

    def test_intake_in_supported_categories(self):
        assert "intake" in SUPPORTED_CATEGORIES

    def test_registry_profile_is_part_profile_instance(self):
        assert isinstance(PART_PROFILES["intake"], PartProfile)

    def test_intake_base_gain_is_4_percent(self):
        assert INTAKE_BASE_GAIN == pytest.approx(0.04)
