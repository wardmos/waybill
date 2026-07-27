# Parallel Delegation Correlation Case

## Parent Decision Goal

Decide whether a child result for the preferences task belongs to either of two parallel delegation requests.

Two requests were active at the same time:

- `request-preferences/` has request ID `preferences-001` and is bounded to preferences serialization.
- `request-retry/` has request ID `retry-002` and is bounded to queue retry accounting.

The child content under `result/` changes `app/preferences.py` and `tests/test_preferences.py`, so its semantics match `preferences-001`. Its metadata instead declares `result_for: retry-002`. This result must be rejected even though the roles and repository state otherwise match.

## Import Classification

- Kind: `delegation_result`
- Status: `rejected`

## Test State

The child reports that the focused preferences test passed, but the parent has not independently verified it.

## Risks / Unknowns

- The result content matches request preferences-001.
- The result_for field incorrectly references retry-002.
- Accepting by agent roles alone would attach work to the wrong task.

## Next Recommended Step

Reject this pairing, preserve both requests, and require a result whose result_for matches preferences-001.
