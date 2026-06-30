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

Inspect a specific bundle:

```bash
./cli/waybill inspect .waybill
```

Create a redacted copy:

```bash
./cli/waybill redact .waybill --output .waybill-redacted
```

Pack a validated bundle:

```bash
./cli/waybill pack .waybill-redacted --output waybill.zip
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
- OpenCode command and skill frontmatter.
- CLI bundle validation behavior through shared validation code.
- CLI bundle inspection output for metadata, artifacts, and validation status.
- CLI redaction output for common token and key/value patterns.
- CLI pack output and refusal to archive invalid bundles.

The script intentionally uses only the Python standard library.

## CLI Redaction Smoke Test

Create a temporary bundle containing synthetic secrets, then redact it:

```bash
./cli/waybill redact /tmp/waybill-secret-fixture --output /tmp/waybill-secret-redacted --force
```

Expected result:

- The output directory is created separately from the source bundle.
- Secret-like values are replaced with `[REDACTED]`.
- The original source bundle is not modified.
- Existing output is refused unless `--force` is provided.

## CLI Pack Smoke Test

Pack a valid bundle:

```bash
./cli/waybill pack examples/claude-to-codex --output /tmp/waybill-example.zip --force
```

Expected result:

- The command validates the bundle before packing.
- A zip archive is created at the output path.
- The archive contains the bundle files under one top-level directory.
- Existing output is refused unless `--force` is provided.
- Invalid bundles are refused and no archive is written.

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

## OpenCode Smoke Test

This repository includes project-scoped OpenCode commands and skills:

```text
.opencode/commands/handoff.md
.opencode/commands/waybill.md
.opencode/skills/handoff/SKILL.md
.opencode/skills/waybill/SKILL.md
```

To smoke test them in OpenCode:

1. Start OpenCode from the repository root:

   ```bash
   opencode
   ```

2. Run:

   ```text
   /handoff import examples/claude-to-codex
   ```

3. Run the alias:

   ```text
   /waybill import examples/claude-to-codex
   ```

Expected result:

- OpenCode loads the project command and handoff skill.
- OpenCode reads the example bundle.
- OpenCode checks the current repository state.
- OpenCode reports that the example bundle references a different app repo.
- OpenCode does not apply `diff.patch`.

Non-interactive smoke test:

```bash
opencode run --command handoff \
  "import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

Expected result:

- OpenCode loads the `handoff` skill.
- OpenCode reads the example bundle artifacts.
- OpenCode runs read-only git state checks.
- OpenCode identifies the repo mismatch.
- OpenCode exits successfully without modifying files.

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
