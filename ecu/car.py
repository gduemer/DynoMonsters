"""Car model for DynoMonsters.

Stores the base physical properties of a vehicle used as inputs to the
dyno generator, ECU optimizer, and biome modifier.

Fields
------
vehicle_id      : unique string identifier
make            : manufacturer name (e.g. "Toyota")
model           : model name (e.g. "Supra")
year            : model year (e.g. 1998)
base_torque_nm  : peak torque at the crank in Newton-metres
weight_kg       : kerb weight in kilograms
redline_rpm     : engine redline in RPM
aspiration      : "NA" | "Turbo" | "Supercharged"
drivetrain      : "FWD" | "RWD" | "AWD"
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

VALID_ASPIRATIONS: frozenset[str] = frozenset({"NA", "Turbo", "Supercharged"})
VALID_DRIVETRAINS: frozenset[str] = frozenset({"FWD", "RWD", "AWD"})


@dataclass
class Car:
    """Immutable-ish vehicle specification used throughout the DynoMonsters engine."""

    vehicle_id: str
    make: str
    model: str
    year: int
    base_torque_nm: float
    weight_kg: float
    redline_rpm: int
    aspiration: str = "NA"
    drivetrain: str = "RWD"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty list means valid)."""
        errors: list[str] = []

        if not self.vehicle_id or not isinstance(self.vehicle_id, str):
            errors.append("vehicle_id must be a non-empty string")

        if not self.make or not isinstance(self.make, str):
            errors.append("make must be a non-empty string")

        if not self.model or not isinstance(self.model, str):
            errors.append("model must be a non-empty string")

        if not isinstance(self.year, int) or self.year < 1886 or self.year > 2100:
            errors.append(
                f"year must be an integer between 1886 and 2100, got {self.year!r}"
            )

        if not isinstance(self.base_torque_nm, (int, float)) or not math.isfinite(
            self.base_torque_nm
        ) or self.base_torque_nm <= 0:
            errors.append(
                f"base_torque_nm must be a positive finite number, got {self.base_torque_nm!r}"
            )

        if not isinstance(self.weight_kg, (int, float)) or not math.isfinite(
            self.weight_kg
        ) or self.weight_kg <= 0:
            errors.append(
                f"weight_kg must be a positive finite number, got {self.weight_kg!r}"
            )

        if not isinstance(self.redline_rpm, int) or self.redline_rpm <= 0:
            errors.append(
                f"redline_rpm must be a positive integer, got {self.redline_rpm!r}"
            )

        if self.aspiration not in VALID_ASPIRATIONS:
            errors.append(
                f"aspiration must be one of {sorted(VALID_ASPIRATIONS)}, "
                f"got {self.aspiration!r}"
            )

        if self.drivetrain not in VALID_DRIVETRAINS:
            errors.append(
                f"drivetrain must be one of {sorted(VALID_DRIVETRAINS)}, "
                f"got {self.drivetrain!r}"
            )

        return errors

    def is_valid(self) -> bool:
        """Return True if the Car passes all validation checks."""
        return len(self.validate()) == 0

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "vehicle_id": self.vehicle_id,
            "make": self.make,
            "model": self.model,
            "year": self.year,
            "base_torque_nm": self.base_torque_nm,
            "weight_kg": self.weight_kg,
            "redline_rpm": self.redline_rpm,
            "aspiration": self.aspiration,
            "drivetrain": self.drivetrain,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Car":
        """Deserialise from a plain dict.

        Raises ``KeyError`` if required fields are missing.
        Raises ``ValueError`` if the resulting Car fails validation.
        """
        car = cls(
            vehicle_id=str(data["vehicle_id"]),
            make=str(data["make"]),
            model=str(data["model"]),
            year=int(data["year"]),
            base_torque_nm=float(data["base_torque_nm"]),
            weight_kg=float(data["weight_kg"]),
            redline_rpm=int(data["redline_rpm"]),
            aspiration=str(data.get("aspiration", "NA")),
            drivetrain=str(data.get("drivetrain", "RWD")),
        )
        errors = car.validate()
        if errors:
            raise ValueError(f"Invalid Car data: {errors}")
        return car

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Car(vehicle_id={self.vehicle_id!r}, make={self.make!r}, "
            f"model={self.model!r}, year={self.year}, "
            f"base_torque_nm={self.base_torque_nm}, weight_kg={self.weight_kg}, "
            f"redline_rpm={self.redline_rpm}, aspiration={self.aspiration!r}, "
            f"drivetrain={self.drivetrain!r})"
        )
