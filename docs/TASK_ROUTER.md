Autonomous Work Selection Engine

1. Mission

Agents must continuously reduce backlog size while preserving build stability.

Work must be:

Small

Isolated

Reversible

Testable

Never pause waiting for perfection.

2. Selection Algorithm (Mandatory)

Agents follow this exact priority order:

Step 1 — Select by Size

Pick only:

XS

S

Never pick M unless explicitly assigned.

Step 2 — Select by Risk

Prefer tasks that:

Add tests

Add validation

Add logging clarity

Improve determinism

Improve contract safety

Avoid:

Architectural refactors

Cross-cutting changes

Multi-system modifications

Step 3 — Select by Impact

Prefer tasks that:

Increase safety

Improve confidence

Enable other tasks

Step 4 — If No Valid Task Exists

Create one of the following:

Add missing unit tests for a subsystem

Add validation guards

Improve error reporting

Improve schema validation

Never sit idle.

3. Parallel Agent Rules

Multiple agents may:

Work on separate backlog IDs

Review each other’s PRs

Create follow-up issues

They must NOT:

Modify the same subsystem without coordination

Refactor shared interfaces

Change contract version unless assigned

4. Escalation Protocol

If a task appears larger than expected:

Complete the smallest safe subset

Open follow-up issues for remaining work

Document limitations clearly

Shipping partial improvements is preferred over delaying.

5. Stability First Principle

If a change:

Compiles

Passes tests

Does not violate constraints

Does not break contract

It is acceptable to merge.

Imperfections become backlog items.