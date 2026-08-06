# Testing Waybill

This document describes checks for the agent-native Waybill handoff workflow,
its optional bundled checker, and the enhanced support CLI.

## Full Local Gate

Run the same deterministic checks used for release readiness:

```bash
python3 -m unittest discover -s tests -t . -v
python3 scripts/validate-waybill.py
python3 -m py_compile cli/waybill waybill_core/*.py scripts/*.py
scripts/sync-adapters.py --check
scripts/smoke-agents.sh --dry-run
python3 scripts/test-wheel-install.py
git diff --check
```

Tests are organized by purpose:

```text
tests/unit/         isolated library and validator behavior
tests/integration/  CLI, repository, adapter, and packaging boundaries
tests/conformance/  deterministic agent observation scenarios
```

All three directories are Python packages so `unittest discover -s tests -t .`
recurses consistently on Python 3.10, 3.11, and 3.12.

The canonical handoff Skill is `skills/handoff/SKILL.md`; its bundle-format,
export, and import references, copyable assets, and single read-only checker are
tested separately from the thin adapter entrypoints. Checker tests run with no
`waybill` executable on `PATH`. `sync-adapters.py --check` verifies every
generated adapter and packaged resource copy.

## Continuous Integration

The `CI` GitHub Actions workflow runs on every push and pull request with a
Python 3.10, 3.11, and 3.12 matrix. Each job runs:

```bash
python3 scripts/validate-waybill.py
python3 -m unittest discover -s tests -t . -v
python3 -m py_compile cli/waybill waybill_core/*.py scripts/*.py
scripts/sync-adapters.py --check
scripts/smoke-agents.sh --dry-run
```

The repository validator checks the workflow triggers, read-only permissions,
Python matrix, action versions, and command list. It runs every named check even
after a validation or unexpected exception, then reports all failures together.
Its packaging check runs `scripts/test-wheel-install.py`, so CI does not repeat
the disposable wheel build as a second workflow step. The validator itself uses
only Python 3.10-compatible standard-library features.

## Repeatable Agent Smoke Tests

When the local agent CLIs are installed and authenticated, run the read-only
import smoke tests with:

```bash
scripts/smoke-agents.sh --tool codex
scripts/smoke-agents.sh --tool opencode
scripts/smoke-agents.sh --tool cursor
scripts/smoke-agents.sh --tool gemini
scripts/smoke-agents.sh --tool claude
```

Run all supported tools in one pass:

```bash
scripts/smoke-agents.sh
```

Print the exact commands without calling any model:

```bash
scripts/smoke-agents.sh --dry-run
```

The script uses `examples/claude-to-codex` by default and requires the working
tree to be clean before and after each tool runs. Command logs are written under
`/tmp`. Before invoking a model, it resolves the selected executable, follows
symbolic links to its real path, hashes its bytes, and verifies the product and
version. Identity checks fail closed. In particular, an executable named
`agent` is not counted as Cursor unless its version or help output identifies it
as Cursor.

Executable paths can be overridden explicitly when a CLI is not on `PATH`:

```bash
WAYBILL_CLAUDE_BINARY=/path/to/claude scripts/smoke-agents.sh --tool claude
WAYBILL_CURSOR_BINARY=/path/to/cursor-agent scripts/smoke-agents.sh --tool cursor
```

Notes:

- These checks call real agent CLIs and may use model credits.
- Some CLIs write local session or log files outside the repository.
- Run these from a normal terminal, not from a restrictive coding-agent sandbox,
  if the CLI needs access to its own local state.
- Gemini CLI in plan mode may not have shell tools available; it should still
  read the bundle and report the repo mismatch from available context.

## Adapter Quality Matrix

The adapter matrix separates installed-binary identity from observed capability
coverage. These are the current minimum gates:

| Adapter | Export | Import |
| --- | --- | --- |
| Claude Code | Required | Required |
| Codex | Required | Required |
| OpenCode | Optional | Required |
| Cursor | Optional | Required |
| Gemini CLI | Optional | Required |

Probe all installed executables without invoking a model:

```bash
python3 scripts/adapter-matrix.py --identity-only
```

The private JSON report includes the requested executable, resolved real path,
SHA-256 digest, detected product, version, observation date, raw identity probe
output, and paths to accepted conformance reports. Keep it with private test
logs in a directory outside this repository, and do not commit it to the public
repository.

Use `--public` only for a sanitized summary. It omits executable paths, raw
output, error detail, and capability-evidence paths while retaining
content-addressed report references and SHA-256 digests:

```bash
python3 scripts/adapter-matrix.py --identity-only --public
```

Capability results come only from separately executed export or import
conformance report JSON files. The matrix command validates and hashes the
reports but never runs an agent model itself. For example, after the
corresponding private runs have been reviewed:

```bash
python3 scripts/adapter-matrix.py \
  --report /private/conformance/claude-code-export.json \
  --report /private/conformance/claude-code-import.json \
  --report /private/conformance/codex-export.json \
  --report /private/conformance/codex-import.json \
  --report /private/conformance/opencode-import.json \
  --report /private/conformance/cursor-import.json \
  --report /private/conformance/gemini-cli-import.json
```

Each accepted report must be a non-dry-run manual observation, contain a
verified executable identity with product, version, observation timestamp, and
executable SHA-256, and cover exactly the complete v1 scenario set for that
capability. Deterministic fake export reports remain CI evidence and cannot
count as real adapter coverage. The matrix probes the executable again and
requires its product, version, and SHA-256 to match the report. A changed binary
therefore produces `evidence_mismatch`; a Grok binary remains
`identity_mismatch` for the Cursor adapter. A report with complete failed
results is retained as `failed`, while a partial or internally inconsistent
report is rejected. The removed `--result ADAPTER:CAPABILITY=STATUS` interface
cannot manufacture capability coverage from an ungrounded status string.

## Agent Conformance

The conformance runner is stricter than the smoke script: each agent must emit
one exact JSON observation, semantic values must match the versioned scenario,
and the runner independently measures all workspace writes outside `.git`.

Validate all scenarios without resolving or executing an agent command:

```bash
python3 scripts/conformance-agents.py \
  --agent-name codex \
  --adapter codex \
  --agent-command 'codex exec --ephemeral -s read-only -C . -' \
  --dry-run
```

The minimum real-agent gate covers an ordinary handoff plus both sides of a
delegation pair:

```bash
python3 scripts/conformance-agents.py \
  --agent-name codex \
  --adapter codex \
  --agent-command 'codex exec --ephemeral -s read-only -C . -' \
  --scenario ordinary-unfinished \
  --scenario delegation-request \
  --scenario delegation-result \
  --timeout 240
```

The ordinary scenario must return `handoff_kind: "handoff"`; every bundled
scenario requires an empty measured-write list. If an optional agent CLI is not
installed, record the coverage gap rather than installing it as part of a test
run. See `CONFORMANCE.md` for the full fourteen-scenario matrix.

Install project-local adapters into a target repository:

```bash
./cli/waybill init --target /tmp/waybill-init-target --dry-run
./cli/waybill init --target /tmp/waybill-init-target
./cli/waybill init --target /tmp/waybill-init-target --force --json
```

`init` and `doctor` cover the file-based project adapters:
`claude-code`, `opencode`, `cursor`, and `gemini-cli`. The Codex adapter is a
local plugin installed from the repo marketplace, not an `init` target.

Check adapter installation:

```bash
./cli/waybill doctor --target /tmp/waybill-init-target
./cli/waybill doctor --target /tmp/waybill-init-target --json
```

Create a draft bundle:

```bash
./cli/waybill new --output /tmp/waybill-draft --repo . --force
./cli/waybill new --output /tmp/waybill-draft --repo . --force --json
```

Compare bundle metadata with a repo:

```bash
./cli/waybill verify-repo .waybill --repo .
./cli/waybill verify-repo .waybill --repo . --json
```

Verify a delegation request/result pair:

```bash
./cli/waybill verify-pair examples/claude-parent-codex-child-request examples/claude-parent-codex-child-result --json
```

Run the full import preflight check:

```bash
./cli/waybill preflight .waybill --repo .
./cli/waybill preflight .waybill --repo . --json
```

Check whether a bundle is ready for handoff:

```bash
./cli/waybill ready .waybill --repo .
./cli/waybill ready .waybill --repo . --json
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
./cli/waybill redact .waybill --output .waybill-redacted --json
```

Create a redacted zip archive:

```bash
./cli/waybill share .waybill --check
./cli/waybill share .waybill --check --json
./cli/waybill share .waybill --output waybill.zip
./cli/waybill share .waybill --output waybill.zip --json
```

Pack a validated bundle:

```bash
./cli/waybill pack .waybill-redacted --output waybill.zip
./cli/waybill pack .waybill-redacted --output waybill.zip --json
```

Unpack and validate a zip archive:

```bash
./cli/waybill unpack waybill.zip --output /tmp/waybill-unpacked
./cli/waybill unpack waybill.zip --output /tmp/waybill-unpacked --json
```

Render a Markdown review report:

```bash
./cli/waybill render .waybill-redacted --output waybill-report.md
./cli/waybill render .waybill-redacted --output waybill-report.md --json
```

## JSON CLI Contract

Every command that accepts `--json` must write exactly one JSON object to
stdout and no ordinary text or traceback to stderr. The object has a top-level
boolean `success`, with this invariant:

```text
success == (exit code == 0)
```

Commands that already expose `valid` retain it. The integration matrix tests
successful and failing paths for all JSON-capable commands, including argparse
usage errors and unexpected exceptions.

## Isolated Wheel Installation

Run:

```bash
python3 scripts/test-wheel-install.py
```

The script copies only packaging inputs into a temporary source tree, rejects
symlinks in packaged sources, builds a wheel, installs it into a temporary
virtual environment, and runs outside both the checkout and build copy with
source-path imports disabled. It verifies the package/CLI version, every
packaged adapter template, `init`, deterministic `.waybill-adapters.json`, a
repeat idempotent init, and `doctor` current states. All wheel, venv, and target
files are deleted with the temporary directory; nothing is uploaded.

This checks:

- Required repository files.
- `.waybill/` is ignored by default.
- JSON syntax for schema, examples, and Codex manifest.
- Minimal `metadata.json` shape.
- Codex plugin manifest shape.
- Example artifact references.
- Required `WAYBILL.md` sections.
- Exact loading and dry-run execution of all fourteen import conformance scenarios.
- Delegation request/result fixtures and missing-section negative validation.
- Obvious secret-like strings in examples.
- Agent-neutral handoff wording in examples.
- OpenCode command and skill frontmatter.
- Cursor rule frontmatter and handoff safety rules.
- Gemini CLI skill frontmatter and handoff safety rules.
- Push and pull request CI coverage for Python 3.10, 3.11, and 3.12 with
  read-only permissions.
- Canonical adapter mirror synchronization in read-only check mode.
- CLI adapter plan/apply separation, full conflict preflight, symlink safety,
  atomic deterministic manifests, and text/JSON reporting.
- CLI adapter diagnostics for current, missing, stale, modified, legacy, and
  invalid-manifest installations.
- CLI draft bundle scaffolding in text and JSON.
- Runtime metadata type, timestamp, digest, and nested sensitive-content
  validation.
- Repository fidelity for staged, unstaged, and untracked-path changes without
  capturing untracked contents.
- Untrusted-input boundaries across every adapter import surface.
- CLI repository verification for matching and mismatched branch, HEAD, and
  dirty state.
- CLI import preflight for valid input and combined bundle/repository failures.
- CLI export readiness for unfinished drafts, completed bundles, and repository
  mismatches.
- CLI inspection for artifact status, malformed metadata, and text/JSON output.
- CLI redaction output for common token and key/value patterns in text and JSON.
- CLI share output for redacted archive preparation and fail-closed handling of
  unscannable files in text and JSON.
- CLI read-only share checks, value-free findings, exit semantics, and zero
  output writes.
- CLI pack output and refusal to archive invalid bundles in text and JSON.
- CLI unpack output and validation of unpacked bundles in text and JSON.
- CLI render output for Markdown review reports in text and JSON.
- End-to-end CLI workflow from draft bundle through rendered review report.
- Common JSON success/error envelopes across every JSON-capable command.
- A temporary wheel build, isolated installation, packaged templates, init,
  doctor, and manifest lifecycle outside the source checkout.
- Resource limits for diff capture, bundle file count, single-file size, and
  total bundle size.

The project runtime and repository test code use only the Python standard
library. Wheel construction uses the build requirements already declared in
`pyproject.toml`; it adds no runtime dependency.

## CLI Init Smoke Test

Install adapters into a temporary repository:

```bash
./cli/waybill init --target /tmp/waybill-init-target --dry-run
./cli/waybill init --target /tmp/waybill-init-target --dry-run --json
./cli/waybill init --target /tmp/waybill-init-target --force
./cli/waybill init --target /tmp/waybill-init-target --force --json
```

Expected result:

- Claude Code skills are copied into `.claude/skills/`.
- OpenCode commands and skills are copied into `.opencode/`.
- Cursor rules are copied into `.cursor/rules/`.
- Gemini CLI skills are copied into `.gemini/skills/`.
- Each handoff entrypoint is installed with the shared files in its
  `references/` directory.
- `.gitignore` includes `.waybill/`.
- Dry-run reports `would-create`, `would-update`, `unchanged`, and
  `would-conflict` without writing any file.
- Every conflict is found before an apply writes its first file.
- Existing conflicting regular files are refused unless `--force` is provided;
  force never follows a symlink.
- `.waybill-adapters.json` is written atomically with deterministic sorted
  content, file digests, and no timestamp.
- `--adapter claude-code` installs only Claude Code skill files.
- `--adapter opencode` installs only OpenCode files.
- `--adapter cursor` installs only Cursor rule files.
- `--adapter gemini-cli` installs only Gemini CLI skill files.
- Codex plugin files are not installed by `init`; see `INSTALL.md`.
- JSON output includes a boolean `success`, dry-run state, conflict state, and
  adapter actions.

## CLI Doctor Smoke Test

Check an initialized repository:

```bash
./cli/waybill doctor --target /tmp/waybill-init-target
./cli/waybill doctor --target /tmp/waybill-init-target --json
```

Expected result:

- Installed Claude Code, OpenCode, Cursor, and Gemini CLI files are `current`.
- `.gitignore` with `.waybill/` is reported as `OK`.
- JSON output includes adapter check status and lifecycle `state` values.
- Deleted managed files are `missing`; files unchanged since an older manifest
  but different from current templates are `stale`; locally changed files are
  `modified`.
- Without a manifest, exact template matches are `current`, while differing
  legacy files are `modified` rather than `stale`.
- A partial installation returns a non-zero exit code and reports missing files.
- `--adapter claude-code` checks only Claude Code skill files.
- `--adapter opencode` checks only OpenCode files.
- `--adapter cursor` checks only Cursor rule files.
- `--adapter gemini-cli` checks only Gemini CLI skill files.
- Codex plugin files are checked by static repository validation, not
  `doctor --adapter`.

## CLI New Smoke Test

Create a draft bundle from the current repository:

```bash
./cli/waybill new --output /tmp/waybill-draft --repo . --force
./cli/waybill new --output /tmp/waybill-draft --repo . --force --json
```

Expected result:

- The command writes the five standard Waybill files.
- `metadata.json` records the current branch, HEAD, and dirty state.
- `diff.patch` captures the current tracked diff, or records that no tracked
  diff was captured.
- JSON output parses as valid JSON and includes output, repo, source agent,
  dirty state, and generated files.
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

## CLI Verify Pair Smoke Test

Verify the synthetic delegation fixtures:

```bash
./cli/waybill verify-pair \
  examples/claude-parent-codex-child-request \
  examples/claude-parent-codex-child-result
```

Expected result:

- The request `request_id` matches the result `result_for`.
- Parent and child roles remain unchanged in both bundles.
- The request source is the parent and the result source is the child.
- `result_status` is `completed`, `partial`, or `blocked`.
- A mismatched reference, reversed role, source mismatch, or invalid status
  returns non-zero.

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

- Text output includes the schema version status, metadata, artifact status, and
  validation status.
- JSON output parses as valid JSON.
- JSON output includes `schema_version_status`, artifact status, and validation
  issue counts.

## CLI Preflight Smoke Test

Run validation and repo-state checks together:

```bash
./cli/waybill preflight /tmp/waybill-draft --repo .
./cli/waybill preflight /tmp/waybill-draft --repo . --json
```

Expected result:

- The command reports validation errors and warnings.
- The command reports repository state checks.
- JSON output parses as valid JSON and includes validation plus repo checks.
- A generated draft bundle for the current repository returns `PASS`.
- An example bundle targeting another branch returns non-zero.

## CLI Ready Smoke Test

Check whether a bundle is ready to hand off:

```bash
./cli/waybill ready /tmp/waybill-draft --repo .
./cli/waybill ready /tmp/waybill-draft --repo . --json
```

Expected result:

- A draft bundle generated by `waybill new` is refused because it still contains
  TODO or placeholder content.
- JSON output parses as valid JSON and includes validation, repo checks, and
  content checks.
- A completed bundle with matching repo metadata returns `PASS`.
- A bundle whose metadata targets another branch returns non-zero.

## CLI Redaction Smoke Test

Create a temporary bundle containing synthetic secrets, then redact it:

```bash
./cli/waybill redact /tmp/waybill-secret-fixture --output /tmp/waybill-secret-redacted --force
./cli/waybill redact /tmp/waybill-secret-fixture --output /tmp/waybill-secret-redacted --force --json
```

Expected result:

- The output directory is created separately from the source bundle.
- Secret-like values are replaced with `[REDACTED]`.
- The original source bundle is not modified.
- Existing output is refused unless `--force` is provided.
- JSON output parses as valid JSON and includes source, output, file count,
  replacement count, and per-file replacement details.

## CLI Share Smoke Test

Check shareability without creating or replacing outputs:

```bash
./cli/waybill share examples/claude-to-codex --check
./cli/waybill share examples/claude-to-codex --check --json
```

Create a redacted review bundle and zip archive in one command:

```bash
./cli/waybill share examples/claude-to-codex --output /tmp/waybill-share.zip --force
./cli/waybill share examples/claude-to-codex --output /tmp/waybill-share.zip --force --json
```

Expected result:

- Check mode does not require `--output` and leaves the entire workspace
  unchanged.
- Check mode exits zero exactly when the bundle is shareable.
- Check findings contain only `kind`, `path`, `count`, and `blocking`; they
  never include matched secret values.
- The command creates a redacted review bundle near the output archive.
- The redacted review bundle is validated before packing.
- The command creates a zip archive from the redacted bundle.
- Existing output is refused unless `--force` is provided.
- Invalid redacted bundles are refused and no archive is written.
- Binary or non-UTF-8 files are refused with their relative paths before any
  share output is created or replaced, including with `--force`.
- JSON output parses as valid JSON and includes source, redacted output,
  archive, redaction, validation, and pack details.

## CLI Pack Smoke Test

Pack a valid bundle:

```bash
./cli/waybill pack examples/claude-to-codex --output /tmp/waybill-example.zip --force
./cli/waybill pack examples/claude-to-codex --output /tmp/waybill-example.zip --force --json
```

Expected result:

- The command validates the bundle before packing.
- A zip archive is created at the output path.
- The archive contains the bundle files under one top-level directory.
- Existing output is refused unless `--force` is provided.
- Invalid bundles are refused and no archive is written.
- JSON output parses as valid JSON and includes validation status, archive root,
  file count, byte count, and packed file details.

## CLI Unpack Smoke Test

Unpack a valid archive:

```bash
./cli/waybill unpack /tmp/waybill-example.zip --output /tmp/waybill-unpacked --force
./cli/waybill unpack /tmp/waybill-example.zip --output /tmp/waybill-unpacked --force --json
```

Expected result:

- The command extracts the archive into the output directory.
- The archive must contain one top-level directory.
- Absolute paths and `..` paths are rejected.
- The unpacked bundle is validated after extraction.
- Existing output is refused unless `--force` is provided.
- JSON output parses as valid JSON and includes archive root, bundle path,
  validation status, file count, byte count, and unpacked file details.

## CLI Render Smoke Test

Render a bundle report:

```bash
./cli/waybill render examples/claude-to-codex --output /tmp/waybill-report.md --force
./cli/waybill render examples/claude-to-codex --output /tmp/waybill-report.md --force --json
```

Expected result:

- The command writes a Markdown report.
- The report includes metadata, artifact status, validation status, and
  `WAYBILL.md` content.
- Rendering to stdout also works when `--output` is omitted.
- JSON output requires `--output` and reports bundle, output, byte count, and
  validation status.
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

The source repository does not track agent-local installation outputs. Generate
the Claude Code files before this smoke test:

```bash
./cli/waybill init --target . --adapter claude-code
```

The generated project-scoped skills are:

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

Generate the OpenCode files before this smoke test:

```bash
./cli/waybill init --target . --adapter opencode
```

The generated project commands and skills are:

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

## Cursor CLI Smoke Test

Generate the Cursor files before this smoke test:

```bash
./cli/waybill init --target . --adapter cursor
```

The generated project rules are:

```text
.cursor/rules/handoff.mdc
.cursor/rules/waybill.mdc
```

To smoke test them with Cursor CLI in read-only ask mode:

```bash
agent -p --trust --mode=ask \
  "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

For scriptable output:

```bash
agent -p --trust --mode=ask --output-format json \
  "handoff import examples/claude-to-codex. Do not modify files; only summarize."
```

Expected result:

- Cursor loads the project rule.
- Cursor reads the example bundle artifacts.
- Cursor checks the current repository state.
- Cursor reports that the example bundle references a different app repo.
- Cursor does not apply `diff.patch`.

## Gemini CLI Smoke Test

Generate the Gemini CLI files before this smoke test:

```bash
./cli/waybill init --target . --adapter gemini-cli
```

The generated workspace skills are:

```text
.gemini/skills/handoff/SKILL.md
.gemini/skills/waybill/SKILL.md
```

To smoke test them in read-only plan mode:

```bash
gemini --skip-trust --approval-mode plan -p \
  "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

For scriptable output:

```bash
gemini --skip-trust --approval-mode plan --output-format json -p \
  "handoff import examples/claude-to-codex. Do not modify files; only summarize."
```

Expected result:

- Gemini CLI discovers the workspace `handoff` skill.
- Gemini CLI reads the example bundle artifacts.
- Gemini CLI checks the current repository state.
- Gemini CLI reports that the example bundle references a different app repo.
- Gemini CLI does not apply `diff.patch`.

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
