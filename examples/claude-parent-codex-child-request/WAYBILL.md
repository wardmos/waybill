# Coding Agent Handoff

## Original Goal

Add a retry limit to a job queue worker so transient failures are retried twice
and permanent failures are surfaced without blocking later jobs.

## Delegation Request

The parent agent has narrowed the work to the retry counter behavior but wants a
child agent to inspect the focused queue worker path before code is changed.

## Child Agent Task

Inspect `src/queue/worker.ts` and `tests/queue-worker.test.ts`. Determine where
retry attempts should be counted and propose the smallest patch that makes the
focused retry-limit test pass.

## Acceptance Criteria

- The child agent identifies the retry counter location.
- The proposed change does not alter successful job processing.
- The child agent records any focused test command it ran or recommends.
- The child agent returns a result bundle instead of applying broad unrelated
  refactors.

## Return Instructions

Export a `delegation_result` bundle with changed files, test state, risks, and
one parent review step. Do not automatically apply a patch in the parent repo.

## Current Status

The queue worker currently retries indefinitely when a transient error keeps
failing. The failing focused test expects the worker to stop after two retries.

Completed:

- Added a focused failing test for retry-limit behavior.
- Confirmed successful jobs still complete in the existing test suite.

Pending:

- Identify the exact retry counter update point.
- Apply or propose the smallest worker change.

## User Constraints

- Keep the change local to queue worker retry behavior.
- Do not introduce a new dependency.
- Prefer focused tests before broad verification.

## Repo State

- Branch: `feature/queue-retry-limit`
- Base ref: `main`
- HEAD SHA: `unknown`
- Dirty: `true`

Relevant git status:

```text
M src/queue/worker.ts
M tests/queue-worker.test.ts
```

## Changed Files

- `tests/queue-worker.test.ts`: Adds a focused retry-limit regression test.
- `src/queue/worker.ts`: Contains the retry loop that needs inspection.

## Commands Run

```text
pnpm test queue-worker
```

Result: failing because the retry-limit test never observes a terminal failure.

## Test State

Passing:

- Existing successful job processing test.

Failing:

- `pnpm test queue-worker`

Not run:

- Full test suite.
- Typecheck.
- Lint.

## Failed Attempts

- Adding a test timeout proved the loop was unbounded but did not identify the
  state update that should stop retries.

## Current Hypothesis

Assumption: the worker records attempts only after a job succeeds, so repeated
transient failures never increment the retry counter.

## Next Recommended Step

Inspect the failure handling branch in `runJob` and find where retry attempts
are persisted before the next queue poll.

## Risks / Unknowns

- Delayed jobs may use the same worker branch.
- Permanent failures may already bypass retry accounting.
- The focused test may not cover concurrency.

## Instructions For Next Agent

Before continuing, inspect the current repository state and compare it with this
handoff. Do not blindly trust this document. Do not apply patches or run
dangerous commands unless the user explicitly asks.
