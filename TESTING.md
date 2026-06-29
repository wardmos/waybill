# Testing Waybill

This document describes the checks for the Claude Code and Codex
handoff flow.

## Static Validation

Run:

```bash
python3 scripts/validate-waybill.py
```

Validate a specific bundle:

```bash
./cli/waybill validate .waybill
```

This checks:

- Required repository files.
- `.waybill/` is ignored by default.
- JSON syntax for schema, examples, and Codex manifest.
- Minimal `metadata.json` shape.
- Codex plugin manifest shape.
- Example artifact references.
- Required `WAYBILL.md` sections.
- Obvious secret-like strings in examples.
- Agent-neutral handoff wording in examples.
- CLI bundle validation behavior through shared validation code.

The script intentionally uses only the Python standard library.

## Manual Test: Claude Code to Codex

Goal: prove that Claude Code can export an unfinished task and Codex can import
it.

1. Open a real or throwaway coding repository in Claude Code.
2. Start a small task and leave it unfinished.
3. Ask Claude Code:

   ```text
   /handoff export
   ```

   The alias should also work:

   ```text
   /waybill export
   ```

4. Confirm `.waybill/` exists with at least:

   ```text
   .waybill/WAYBILL.md
   .waybill/metadata.json
   ```

5. Confirm recommended files exist when useful context was available:

   ```text
   .waybill/diff.patch
   .waybill/commands.log
   .waybill/test-summary.md
   ```

6. Open the same repository in Codex with the Waybill plugin enabled.
7. Ask Codex:

   ```text
   /handoff import .waybill
   ```

   The alias should also work:

   ```text
   /waybill import .waybill
   ```

8. Confirm Codex summarizes:

   - Original goal.
   - Current status.
   - Changed files.
   - Test state.
   - Failed attempts.
   - Risks or unknowns.
   - Next recommended step.

9. Confirm Codex checks current repository state before making changes.
10. Confirm Codex does not automatically apply `diff.patch`.

## Manual Test: Codex to Claude Code

Use the same flow in the opposite direction:

1. Start an unfinished task in Codex.
2. Ask Codex:

   ```text
   /handoff export
   ```

3. Open the same repository in Claude Code.
4. Ask Claude Code:

   ```text
   /handoff import .waybill
   ```

5. Confirm Claude Code summarizes the handoff and compares it with the current
   repository state before continuing.

## Claude Code Skill Smoke Test

This repository includes project-scoped Claude Code skills:

```text
.claude/skills/handoff/SKILL.md
.claude/skills/waybill/SKILL.md
```

To smoke test them in Claude Code:

1. Start Claude Code from the repository root:

   ```bash
   claude
   ```

2. Run:

   ```text
   /handoff import examples/codex-to-claude
   ```

3. Run the alias:

   ```text
   /waybill import examples/codex-to-claude
   ```

Expected result:

- Claude Code loads the repo skill.
- Claude Code reads the example bundle.
- Claude Code checks the current repository state.
- Claude Code reports that the example bundle references a different app repo.
- Claude Code does not apply `diff.patch`.

Then test export:

```text
/handoff export
```

Expected result:

- Claude Code creates `.waybill/`.
- `WAYBILL.md` distinguishes facts, assumptions, and unresolved user intent.
- `commands.log` separates read-only inspection commands from bundle-writing
  actions such as creating `.waybill/` and writing artifact files.
- `diff.patch` does not imply code changed when only the bundle was written.

## Expected Result

The MVP passes when both directions work:

```text
Claude Code unfinished task -> .waybill/ -> Codex continues
Codex unfinished task -> .waybill/ -> Claude Code continues
```

The next agent should understand the task, state, failing checks, risks, and
first action without relying on the original agent session.

## Failure Signals

Treat these as failures:

- `.waybill/` is committed or staged by default.
- Import applies `diff.patch` without explicit user approval.
- Import skips repository state inspection.
- `WAYBILL.md` omits the next recommended step.
- Handoff text says a specific agent must continue.
- Examples contain real tokens, customer data, or private paths.
