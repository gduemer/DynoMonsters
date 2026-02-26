Continuous Integration Contract

CI must protect stability without slowing iteration.

Required CI Jobs
1. Unity Build Check

Project compiles

No new warnings introduced

2. C# Unit Tests

All pass

No flakiness

3. Python Lint

No syntax errors

Deterministic seed test passes

4. ECU Contract Test

Sample request produces valid response

Schema validated

Output within constraint bounds

Determinism Test

Given fixed input and seed:

ECU output must match stored snapshot.

Snapshot drift requires explicit approval.

Performance Guardrails

Soft thresholds:

ECU under 2000ms

Dyno computation under 5ms typical

If exceeded:

CI warns

Does not block merge

Opens auto-created issue

Failure Philosophy

Hard Fail CI Only For:

Compilation failure

Test failure

Contract violation

Determinism failure

Soft Fail (warn only):

Performance regression

Minor lint style issue

Logging noise

Merge Philosophy

If:

CI passes

Review checklist passed

Scope small and isolated

Merge is allowed.

If not perfect:

Merge

Open follow-up issue

Forward motion is preferred over stagnation.

Aggressive Autonomy Model

Agents are expected to:

Continuously reduce backlog

Create follow-up issues instead of bloating PRs

Improve test coverage incrementally

Favor safety improvements over feature spikes

Ship small improvements daily

The system must evolve without destabilizing.

Unity remains authoritative.
Validation remains strict.
Autonomy remains disciplined.