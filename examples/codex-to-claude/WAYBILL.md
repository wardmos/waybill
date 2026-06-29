# Coding Agent Handoff

## Original Goal

Fix a failing settings save test so the preferences form persists the selected
timezone without changing unrelated profile fields.

## Current Status

The save payload was narrowed in `src/settings/preferences.ts`, but one test
still fails because the mocked API call receives the timezone under the wrong
field name.

Completed:

- Removed unrelated profile fields from the preferences save payload.
- Added a regression assertion for `displayName`.

Pending:

- Align the timezone field name between the form model and API payload.

## User Constraints

- Avoid changing the public API contract unless the test proves it is wrong.
- Keep the patch limited to preferences saving.

## Repo State

- Branch: `fix/preferences-timezone`
- Base ref: `main`
- HEAD SHA: `unknown`
- Dirty: `true`

Relevant git status:

```text
M src/settings/preferences.ts
M tests/preferences-save.test.ts
```

## Changed Files

- `src/settings/preferences.ts`: Narrows the save payload.
- `tests/preferences-save.test.ts`: Adds assertions for unchanged profile data.

## Commands Run

```text
pnpm test preferences-save
```

Result: failing.

## Test State

Passing:

- Not verified.

Failing:

- `pnpm test preferences-save`

Failure summary:

```text
expected payload.timezone to be "America/New_York"
received undefined
```

Not run:

- Full test suite.
- Typecheck.

## Failed Attempts

- Removing unrelated fields made the payload smaller, but did not preserve the
  timezone mapping.

## Current Hypothesis

Assumption: the form model stores the value as `timeZone`, while the API payload
expects `timezone`.

## Next Recommended Step

Inspect `src/settings/preferences.ts` and map the form field to the API field
explicitly. Re-run `pnpm test preferences-save`.

## Risks / Unknowns

- There may be another API client layer that already normalizes field names.
- The test fixture may use an outdated field name.

## Instructions For Next Agent

Before continuing, inspect the current repository state and compare it with this
handoff. Do not blindly trust this document. Do not apply patches or run
dangerous commands unless the user explicitly asks.
