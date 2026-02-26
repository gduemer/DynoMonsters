# DynoMonsters Architecture

## 1. Goal
Deliver tuning that feels real without turning the game into a spreadsheet.
Unity owns gameplay truth. Python ECU proposes small improvements within safe bounds.

## 2. High-Level Components

### 2.1 Unity Client (C#)
Authoritative for:
- Vehicle state
- Part inventory and equipped parts
- Dyno curve generation
- Environment effects (biome modifiers)
- Street Cred progression
- Validation and clamping of any ECU proposal
- Saving the player build and tune

### 2.2 ECU Service (Python, invoked as a subprocess)
Responsible for:
- Taking a baseline torque curve + constraints
- Running N learning cycles (Street Cred affects N)
- Returning a proposal that improves the curve slightly within constraints
- Producing deterministic output when a seed is provided

Python is not authoritative. It is a tuning assistant.

## 3. Data Ownership Rules
- Unity is the source of truth for all gameplay state.
- Python receives inputs, returns a proposal.
- Unity validates proposal and applies only if it passes checks.
- Unity persists the final applied tune.

If Python output is invalid, Unity rejects it and falls back to baseline.

## 4. Dyno Model

### 4.1 Core formula
Horsepower is derived from torque and RPM:

HP = (Torque * RPM) / 5252

### 4.2 Curve representation
We represent curves by RPM bins:
- rpm_bins: integer array, monotonic ascending
- torque_nm: float array, same length as rpm_bins

Unity computes:
- hp: float array derived per bin
- peaks: peak torque, peak HP, and RPM locations

## 5. Parts as Potential Range
Parts never directly add a fixed HP value.
Each part contributes constraints and potential ranges, for example:
- turbo_efficiency_range
- afr_target_range
- ignition_timing_advance_range
- boost_target_range
- cooling_capacity_range

Unity combines all equipped parts into a single constraints object that Python must respect.

## 6. Tuning and the ECU Learning Loop

### 6.1 What "learning" means in gameplay terms
Python does not simulate full engine physics.
It searches within allowed calibration bounds to produce a small improvement.
Improvements are limited and smooth, so the result feels like an ECU dial-in.

### 6.2 Street Cred modifier
Street Cred increases:
- learning cycles budget
- exploration depth (still bounded)

Street Cred never breaks the hard cap on gains.
Target: 0% to 2% peak improvement relative to baseline for a good combo.

### 6.3 Determinism
All ECU runs must be reproducible:
- Unity provides a seed
- Python uses seed for any randomness
- Same inputs + same seed must yield identical outputs

## 7. Environment and GPS Biomes

Unity computes a biome context from GPS:
- altitude_m
- ambient_temp_c
- biome_id

Biome modifiers:
- High altitude reduces air density. NA loses more than turbo.
- High temperature increases wear and makes cooling parts more important.

Biome affects:
- baseline torque curve generation
- wear and cooling requirements

Python receives the environment context only to adjust the search constraints.
Unity remains authoritative for the final environment effects.

## 8. Trading and Proximity Gate
- Trading UI opens only if two players are within 100m.
- Unity uses a distance function (Haversine) to determine proximity.
- The server (or authoritative host) should validate proximity for real trades.
- If offline only, enforce local proximity check and log all trades.

## 9. Execution Model

### 9.1 Subprocess interface (Phase 0)
Unity runs:
python ecu_runner.py

Unity writes JSON to stdin.
Python writes JSON to stdout.
All logs go to stderr.

Timeout rules:
- Unity sets a short timeout (example: 2 seconds) for ECU runs.
- On timeout, Unity cancels and uses baseline.

### 9.2 Future service (Phase 1)
The same contract can be exposed via local HTTP.
No gameplay logic changes required if the contract stays the same.

## 10. Validation and Safety Gates (Unity)
Unity must reject any ECU proposal that violates:
- NaN or infinity values
- RPM bins mismatch
- torque deltas exceeding per-bin max change
- peak gain exceeding cap (default 2%)
- curve smoothness constraints violated
- any calibration parameter outside allowed range

If rejected:
- log reason
- return baseline tune