"""Tests for ecu.wear — Wear and Tear algorithm."""

from __future__ import annotations

import math
import pytest

from ecu.wear import (
    WEAR_PER_RACE,
    MIN_CONDITION,
    MAX_CONDITION,
    apply_race_wear,
    apply_wear_to_parts,
    races_until_worn_out,
)


# ---------------------------------------------------------------------------
# apply_race_wear — core behaviour
# ---------------------------------------------------------------------------

class TestApplyRaceWear:
    def test_one_race_reduces_by_one_percent(self):
        """1 race must reduce condition by exactly WEAR_PER_RACE (1 %)."""
        result = apply_race_wear(1.0, races=1)
        assert result == pytest.approx(1.0 - WEAR_PER_RACE)

    def test_default_races_is_one(self):
        result = apply_race_wear(0.5)
        assert result == pytest.approx(0.5 - WEAR_PER_RACE)

    def test_multiple_races(self):
        result = apply_race_wear(1.0, races=10)
        assert result == pytest.approx(1.0 - 10 * WEAR_PER_RACE)

    def test_zero_races_no_change(self):
        assert apply_race_wear(0.75, races=0) == pytest.approx(0.75)

    def test_clamps_to_zero_not_negative(self):
        """Condition must never go below 0.0."""
        result = apply_race_wear(0.005, races=1)
        assert result == pytest.approx(0.0)

    def test_already_zero_stays_zero(self):
        assert apply_race_wear(0.0, races=1) == pytest.approx(0.0)

    def test_full_condition_after_100_races_is_zero(self):
        result = apply_race_wear(1.0, races=100)
        assert result == pytest.approx(0.0)

    def test_result_never_exceeds_max_condition(self):
        result = apply_race_wear(MAX_CONDITION, races=0)
        assert result <= MAX_CONDITION

    def test_result_never_below_min_condition(self):
        result = apply_race_wear(MIN_CONDITION, races=1000)
        assert result >= MIN_CONDITION

    def test_wear_per_race_constant_is_one_percent(self):
        assert WEAR_PER_RACE == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# apply_race_wear — input validation
# ---------------------------------------------------------------------------

class TestApplyRaceWearValidation:
    def test_nan_condition_raises(self):
        with pytest.raises(ValueError, match="finite"):
            apply_race_wear(float("nan"))

    def test_inf_condition_raises(self):
        with pytest.raises(ValueError, match="finite"):
            apply_race_wear(float("inf"))

    def test_condition_above_1_raises(self):
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            apply_race_wear(1.001)

    def test_condition_below_0_raises(self):
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            apply_race_wear(-0.001)

    def test_negative_races_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            apply_race_wear(0.5, races=-1)

    def test_float_races_raises(self):
        with pytest.raises((ValueError, TypeError)):
            apply_race_wear(0.5, races=1.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# apply_wear_to_parts
# ---------------------------------------------------------------------------

class TestApplyWearToParts:
    def _make_parts(self, conditions: list[float]) -> list[dict]:
        return [
            {"part_id": f"part-{i}", "condition": c}
            for i, c in enumerate(conditions)
        ]

    def test_single_part_one_race(self):
        parts = self._make_parts([1.0])
        result = apply_wear_to_parts(parts, races=1)
        assert result[0]["condition"] == pytest.approx(1.0 - WEAR_PER_RACE)

    def test_multiple_parts_all_worn(self):
        parts = self._make_parts([1.0, 0.5, 0.2])
        result = apply_wear_to_parts(parts, races=1)
        assert result[0]["condition"] == pytest.approx(1.0 - WEAR_PER_RACE)
        assert result[1]["condition"] == pytest.approx(0.5 - WEAR_PER_RACE)
        assert result[2]["condition"] == pytest.approx(0.2 - WEAR_PER_RACE)

    def test_does_not_mutate_originals(self):
        parts = self._make_parts([1.0])
        apply_wear_to_parts(parts, races=1)
        assert parts[0]["condition"] == 1.0  # original unchanged

    def test_preserves_other_fields(self):
        parts = [{"part_id": "turbo-1", "level": 3, "condition": 0.8}]
        result = apply_wear_to_parts(parts, races=1)
        assert result[0]["part_id"] == "turbo-1"
        assert result[0]["level"] == 3

    def test_empty_parts_list(self):
        assert apply_wear_to_parts([], races=5) == []

    def test_clamps_worn_out_parts(self):
        parts = self._make_parts([0.005])
        result = apply_wear_to_parts(parts, races=1)
        assert result[0]["condition"] == pytest.approx(0.0)

    def test_zero_races_no_change(self):
        parts = self._make_parts([0.7, 0.3])
        result = apply_wear_to_parts(parts, races=0)
        assert result[0]["condition"] == pytest.approx(0.7)
        assert result[1]["condition"] == pytest.approx(0.3)

    def test_negative_races_raises(self):
        parts = self._make_parts([1.0])
        with pytest.raises(ValueError, match="non-negative"):
            apply_wear_to_parts(parts, races=-1)

    def test_missing_condition_defaults_to_max(self):
        parts = [{"part_id": "no-condition"}]
        result = apply_wear_to_parts(parts, races=1)
        assert result[0]["condition"] == pytest.approx(MAX_CONDITION - WEAR_PER_RACE)


# ---------------------------------------------------------------------------
# races_until_worn_out
# ---------------------------------------------------------------------------

class TestRacesUntilWornOut:
    def test_full_condition_is_100_races(self):
        assert races_until_worn_out(1.0) == 100

    def test_half_condition_is_50_races(self):
        assert races_until_worn_out(0.5) == 50

    def test_zero_condition_is_zero_races(self):
        assert races_until_worn_out(0.0) == 0

    def test_result_is_integer(self):
        result = races_until_worn_out(0.75)
        assert isinstance(result, int)

    def test_floors_fractional_races(self):
        # 0.015 / 0.01 = 1.5 → floor → 1
        assert races_until_worn_out(0.015) == 1

    def test_nan_raises(self):
        with pytest.raises(ValueError, match="finite"):
            races_until_worn_out(float("nan"))

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            races_until_worn_out(1.5)
