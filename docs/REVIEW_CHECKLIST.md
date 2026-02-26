Mandatory Review Framework

Each PR must be reviewed by two AI reviewers using this checklist.

Reviewer A — Correctness

Must verify:

Math and Physics

HP formula correct

No incorrect unit mixing

No silent rounding errors

Boundaries

No NaN

No infinity

No divide-by-zero

No array mismatch

Proper clamp enforcement

ECU Rules

Peak gain cap enforced

Delta limits enforced

Smoothness constraint respected

Determinism preserved with seed

Environment

Biome effects isolated

No hidden side effects

Reviewer B — Maintainability

Must verify:

Structure

Small cohesive classes

No god objects

Clear method names

No duplicated logic

Dependencies

No new heavy dependencies

No hidden coupling

No unnecessary abstraction layers

Readability

Clear variable names

No cryptic one-liners

No speculative complexity

Automatic Rejection Conditions

PR must be rejected if:

Breaks contract schema

Introduces non-deterministic behavior

Removes validation logic

Increases ECU gain cap

Introduces embedded Python runtime

Adds blocking logic to Unity main thread

Soft Warnings (Create Issue Instead)

Minor performance inefficiency

UI roughness

Naming inconsistency

Suboptimal logging

These should NOT block merge.
Create follow-up issues instead.