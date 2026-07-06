# Waybill Handoff Import

Use this command when the user asks for any of:

```text
/handoff import .waybill
/waybill import .waybill
handoff import .waybill
waybill import .waybill
import a waybill
continue from a waybill
```

Import a Waybill Bundle and prepare to continue the task.

## Rules

- Read the bundle before acting.
- Verify the current repository state before trusting the bundle.
- Do not automatically apply `diff.patch`.
- Do not run dangerous commands.
- Do not assume the source agent is available.
- Keep the continuation agent-neutral unless the user asks for agent-specific
  output.

## Procedure

1. Locate the bundle path. Use `.waybill/` when the user does not provide one.
2. Read `WAYBILL.md`.
3. Read `metadata.json`.
4. Read recommended artifacts when present:
   - `diff.patch`
   - `commands.log`
   - `test-summary.md`
5. Inspect the current repository with read-only commands when available:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
6. Compare the bundle's repo state with the current repo state.
7. Check optional `metadata.json` `handoff.kind`. If it is
   `delegation_request`, treat the bundle as a bounded child-agent task. If it
   is `delegation_result`, treat the bundle as advisory output for parent-agent
   review.
8. Summarize:
   - Original goal
   - Handoff kind
   - Current status
   - Changed files
   - Test state
   - Failed attempts
   - Risks and unknowns
   - Next recommended step
9. Continue only after grounding the next step in the current repo.

## Final Response

Before making changes, state:

- What the handoff says
- What the current repo state says
- Any mismatch
- The next action you are taking
