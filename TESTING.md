# Testing Waybill

This document describes the checks for the Claude Code and Codex
handoff flow.

## Static Validation

Run:

```bash
python3 scripts/validate-waybill.py
```

Install project-local adapters into a target repository:

```bash
./cli/waybill init --target /tmp/waybill-init-target
```

Check adapter installation:

```bash
./cli/waybill doctor --target /tmp/waybill-init-target
```

Create a draft bundle:

```bash
./cli/waybill new --output /tmp/waybill-draft --repo . --force
```

Compare bundle metadata with a repo:

```bash
./cli/waybill verify-repo .waybill --repo .
./cli/waybill verify-repo .waybill --repo . --json
```

Run the full import preflight check:

```bash
./cli/waybill preflight .waybill --repo .
```

Check whether a bundle is ready for handoff:

```bash
./cli/waybill ready .waybill --repo .
```

Validate a specific bundle:

```bash
./cli/waybill validate .waybill
./cli/waybill validate .waybill --json
```

Inspect a specific bundle:

```bash
./cli/waybill inspect .waybill
./cli/waybill inspect .waybill --json
```

Create a redacted copy:

```bash
./cli/waybill redact .waybill --output .waybill-redacted
```

Create a redacted zip archive:

```bash
./cli/waybill share .waybill --output waybill.zip
```

Pack a validated bundle:

```bash
./cli/waybill pack .waybill-redacted --output waybill.zip
```

Unpack and validate a zip archive:

```bash
./cli/waybill unpack waybill.zip --output /tmp/waybill-unpacked
```

Render a Markdown review report:

```bash
./cli/waybill render .waybill-redacted --output waybill-report.md
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
- CLI adapter initialization into target repositories.
- CLI adapter installation checks.
- CLI draft bundle scaffolding.
- CLI import preflight checks.
- CLI export readiness checks for draft placeholders.
- CLI repository-state verification against bundle metadata in text and JSON.
- CLI bundle validation behavior through text and JSON output.
- CLI bundle inspection output for text and JSON reports.
- CLI redaction output for common token and key/value patterns.
- CLI share output for redacted archive preparation.
- CLI pack output and refusal to archive invalid bundles.
- CLI unpack output and validation of unpacked bundles.
- CLI render output for Markdown review reports.

The script intentionally uses only the Python standard library.

## CLI Init Smoke Test

Install adapters into a temporary repository:

```bash
./cli/waybill init --target /tmp/waybill-init-target --force
```

Expected result:

- Claude Code skills are copied into `.claude/skills/`.
- OpenCode commands and skills are copied into `.opencode/`.
- `.gitignore` includes `.waybill/`.
- Existing adapter files are refused unless `--force` is provided.
- `--adapter opencode` installs only OpenCode files.

## CLI Doctor Smoke Test

Check an initialized repository:

```bash
./cli/waybill doctor --target /tmp/waybill-init-target
```

Expected result:

- Installed Claude Code and OpenCode files are reported as `OK`.
- `.gitignore` with `.waybill/` is reported as `OK`.
- A partial installation returns a non-zero exit code and reports missing files.
- `--adapter opencode` checks only OpenCode files.

## CLI New Smoke Test

Create a draft bundle from the current repository:

```bash
./cli/waybill new --output /tmp/waybill-draft --repo . --force
```

Expected result:

- The command writes the five standard Waybill files.
- `metadata.json` records the current branch, HEAD, and dirty state.
- `diff.patch` captures the current tracked diff, or records that no tracked
  diff was captured.
- The generated bundle passes `./cli/waybill validate`.
- Existing standard files are refused unless `--force` is provided.

## CLI Verify Repo Smoke Test

Compare an example bundle with the current repository:

```bash
./cli/waybill verify-repo examples/claude-to-codex --repo .
./cli/waybill verify-repo examples/claude-to-codex --repo . --json
```

Expected result:

- The command reads `metadata.json`.
- The command checks the target repo branch, HEAD, and dirty state.
- The example bundle reports a mismatch against the Waybill repository.
- JSON output parses as valid JSON and includes `valid` plus check details.
- A synthetic bundle with matching current repo metadata returns `PASS`.

## CLI Validate Smoke Test

Validate a bundle in text and JSON modes:

```bash
./cli/waybill validate examples/claude-to-codex
./cli/waybill validate examples/claude-to-codex --json
```

Expected result:

- Text output reports `PASS` for a valid bundle.
- JSON output parses as valid JSON.
- JSON output includes `valid`, error count, warning count, and issue details.
- Invalid bundles return non-zero in both modes.

## CLI Inspect Smoke Test

Inspect bundle metadata and validation status:

```bash
./cli/waybill inspect examples/claude-to-codex
./cli/waybill inspect examples/claude-to-codex --json
```

Expected result:

- Text output includes metadata, artifact status, and validation status.
- JSON output parses as valid JSON.
- JSON output includes artifact status and validation issue counts.

## CLI Preflight Smoke Test

Run validation and repo-state checks together:

```bash
./cli/waybill preflight /tmp/waybill-draft --repo .
```

Expected result:

- The command reports validation errors and warnings.
- The command reports repository state checks.
- A generated draft bundle for the current repository returns `PASS`.
- An example bundle targeting another branch returns non-zero.

## CLI Ready Smoke Test

Check whether a bundle is ready to hand off:

```bash
./cli/waybill ready /tmp/waybill-draft --repo .
```

Expected result:

- A draft bundle generated by `waybill new` is refused because it still contains
  TODO or placeholder content.
- A completed bundle with matching repo metadata returns `PASS`.
- A bundle whose metadata targets another branch returns non-zero.

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

## CLI Share Smoke Test

Create a redacted review bundle and zip archive in one command:

```bash
./cli/waybill share examples/claude-to-codex --output /tmp/waybill-share.zip --force
```

Expected result:

- The command creates a redacted review bundle near the output archive.
- The redacted review bundle is validated before packing.
- The command creates a zip archive from the redacted bundle.
- Existing output is refused unless `--force` is provided.
- Invalid redacted bundles are refused and no archive is written.

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

## CLI Unpack Smoke Test

Unpack a valid archive:

```bash
./cli/waybill unpack /tmp/waybill-example.zip --output /tmp/waybill-unpacked --force
```

Expected result:

- The command extracts the archive into the output directory.
- The archive must contain one top-level directory.
- Absolute paths and `..` paths are rejected.
- The unpacked bundle is validated after extraction.
- Existing output is refused unless `--force` is provided.

## CLI Render Smoke Test

Render a bundle report:

```bash
./cli/waybill render examples/claude-to-codex --output /tmp/waybill-report.md --force
```

Expected result:

- The command writes a Markdown report.
- The report includes metadata, artifact status, validation status, and
  `WAYBILL.md` content.
- Rendering to stdout also works when `--output` is omitted.
- Existing output is refused unless `--force` is provided.
- Output inside the source bundle is refused.

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
