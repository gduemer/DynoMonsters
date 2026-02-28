"""Tests for ecu.dyno_model — core dyno math."""

import pytest

from ecu.dyno_model import (
    HP_CONSTANT,
    apply_torque_deltas,
    compute_hp,
    compute_hp_curve,
    find_peaks,
)


# ── compute_hp ──────────────────────────────────────────────────────────────


class TestComputeHp:
    def test_known_value(self):
        # 300 lb-ft at 5252 RPM == 300 HP exactly
        assert compute_hp(300.0, HP_CONSTANT) == pytest.approx(300.0)

    def test_zero_rpm_returns_zero(self):
        assert compute_hp(500.0, 0) == 0.0

    def test_positive_values(self):
        hp = compute_hp(200.0, 6000)
        assert hp == pytest.approx((200.0 * 6000) / HP_CONSTANT)

    def test_nan_raises(self):
        with pytest.raises(ValueError, match="Non-finite"):
            compute_hp(float("nan"), 3000)

    def test_inf_raises(self):
        with pytest.raises(ValueError, match="Non-finite"):
            compute_hp(float("inf"), 3000)


# ── compute_hp_curve ────────────────────────────────────────────────────────


class TestComputeHpCurve:
    def test_basic_curve(self):
        rpm = [1000, 2000, 3000]
        tq = [100.0, 200.0, 150.0]
        hp = compute_hp_curve(rpm, tq)
        assert len(hp) == 3
        assert hp[0] == pytest.approx((100.0 * 1000) / HP_CONSTANT)

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="mismatch"):
            compute_hp_curve([1000, 2000], [100.0])


# ── find_peaks ──────────────────────────────────────────────────────────────


class TestFindPeaks:
    def test_simple_peaks(self):
        rpm = [1000, 2000, 3000, 4000, 5000, 6000]
        tq = [100.0, 150.0, 200.0, 190.0, 170.0, 140.0]
        peaks = find_peaks(rpm, tq)
        assert peaks.peak_torque_nm == 200.0
        assert peaks.peak_torque_rpm == 3000
        # HP peaks later because HP = TQ * RPM / 5252
        assert peaks.peak_hp_rpm >= 3000

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            find_peaks([], [])


# ── apply_torque_deltas ─────────────────────────────────────────────────────


class TestApplyTorqueDeltas:
    def test_adds_correctly(self):
        tq = [100.0, 200.0, 300.0]
        deltas = [1.0, -2.0, 3.0]
        result = apply_torque_deltas(tq, deltas)
        assert result == [101.0, 198.0, 303.0]

    def test_zero_deltas(self):
        tq = [100.0, 200.0]
        result = apply_torque_deltas(tq, [0.0, 0.0])
        assert result == tq

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="mismatch"):
            apply_torque_deltas([100.0], [1.0, 2.0])

    def test_nan_delta_raises(self):
        with pytest.raises(ValueError, match="Non-finite"):
            apply_torque_deltas([100.0], [float("nan")])
