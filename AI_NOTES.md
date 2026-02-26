DynoMonsters Autonomous Agent Operating Rules

1. Mission

You are working on DynoMonsters, a Unity + Python game project centered around:

Real-feeling dyno tuning

AI-assisted ECU optimization

Biome-based performance modifiers

GPS-based trading constraints

Your goal is to:

Read the documentation in /docs

Select the smallest valid task

Implement safely

Add tests

Open a PR

Request review

You do not merge. Geoff merges.

2. Required Reading Before Any Work

Before writing code, you must read:

docs/20_ARCHITECTURE.md

docs/ECU_CONTRACT.md

docs/10_BACKLOG.md

docs/30_CODING_STANDARDS.md

If these files conflict, architecture wins.

Do not invent systems not described in architecture.

3. Work Selection Rules

You must:

Select only XS or S sized tasks.

Select tasks with no dependencies.

Work on exactly one backlog item per branch.

Never take M size tasks unless explicitly assigned.

If no suitable task exists:

Add tests to improve coverage of an existing feature.

Improve validation safety.

Improve logging clarity.

4. Branching Rules

Create a new branch:

feature/<short-description>

fix/<short-description>

test/<short-description>

Do not commit directly to main.

5. Definition of Done

A task is done only if:

Code compiles (C# and/or Python)

Unit tests pass

No new warnings introduced

Contract rules respected

Validation rules preserved

Determinism preserved where required

PR opened using template

Two reviewers requested

6. Code Review Roles

Each PR must request two AI reviewers:

Reviewer A: Correctness

Must check:

Mathematical correctness

Boundary conditions

Determinism

Validation enforcement

Constraint compliance

No unsafe assumptions

Reviewer B: Maintainability

Must check:

Clarity

Naming

Cohesion

No unnecessary abstractions

No new heavy dependencies

Simplicity over cleverness

Both reviewers must comment before PR is marked ready.

7. Hard Constraints

You must NOT:

Add new frameworks without a backlog item allowing it.

Embed Python into Unity.

Bypass validation logic.

Increase ECU gain caps.

Change contract format without version bump.

Merge PRs.

Perform large refactors.

Introduce network dependencies for ECU.

Unity is authoritative. Python proposes only.

8. ECU System Rules

The ECU is:

A deterministic tuning assistant.

Not authoritative.

Bound by constraints provided by Unity.

Limited to small performance improvements (default cap 2%).

Unity must reject:

NaN or infinity values

Oversized torque deltas

Curve smoothness violations

Peak gains above cap

Out-of-range calibration values

If Python fails:

Unity must fall back to baseline.

Log the reason.

Safety over gain.

9. Autonomy Loop

Every agent follows this loop:

Identify smallest viable task.

Write or update a test first if possible.

Implement minimal change.

Validate against architecture.

Run tests.

Open PR.

Assign reviewers.

Stop.

Do not chain tasks in a single PR.

10. Logging Discipline

No print() in Python.

No Debug.Log spam in Unity.

Structured logging only.

No logging inside tight loops unless debug-flag gated.

11. Determinism Rules

Any logic that:

Uses randomness

Affects dyno results

Affects ECU tuning

Must:

Accept a seed

Produce identical output given identical inputs and seed

Non-deterministic behavior is a defect.

12. Performance Rules

Phase 0 target:

ECU subprocess completes under 2 seconds.

Dyno calculation under 5ms for standard RPM bins.

No blocking calls on main Unity thread longer than necessary.

If performance degrades, create a performance task.

13. GPS and Biome Rules

Biome modifiers must:

Be isolated from ECU logic.

Modify baseline curve before ECU tuning.

Be testable independently.

Never directly modify final tune without validation.

Trading proximity must:

Use deterministic distance calculation.

Be tested with fixed coordinates.

Enforce 100m rule strictly.

14. If You Are Unsure

If a task is ambiguous:

Create a small clarification PR updating documentation.

Do not guess.

Do not invent new architecture.

15. Priority Order for Development

When choosing work, prefer:

Validation and safety

Determinism

Core dyno math

ECU stub implementation

Biome logic

Trading gate

UI polish

Optimization

Safety and correctness before features.

16. Commit Quality Standard

Commits must:

Be small

Be descriptive

Explain why, not just what

Reference backlog ID

Example:
DM-011: Add deterministic ECU stub with bounded torque deltas

17. Final Authority

Unity is authoritative.
Python proposes.
Validation decides.
Geoff merges.

No exceptions.