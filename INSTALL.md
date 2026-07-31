# Install Waybill

Waybill ships as Markdown instructions for Claude Code, a local Codex plugin,
OpenCode commands and skills, Cursor project rules, Gemini CLI workspace
skills, and a small Python standard-library CLI. No package manager install is
required when running it from a Waybill checkout.

For the shortest setup path, start with `QUICKSTART.md`. This document keeps
the fuller per-adapter details.

## Managed Project Adapter Lifecycle

`waybill init` manages the file-based Claude Code, OpenCode, Cursor CLI, and
Gemini CLI adapters. Preview the complete plan before writing:

```bash
./cli/waybill init --target /path/to/repo --dry-run
./cli/waybill init --target /path/to/repo --dry-run --json
```

The plan reports `would-create`, `would-update`, `unchanged`, and
`would-conflict`. It finishes conflict preflight for every selected file before
an apply can begin. `--force` may replace conflicting regular files, but it
never follows a symbolic link.

Apply and verify the plan:

```bash
./cli/waybill init --target /path/to/repo
./cli/waybill doctor --target /path/to/repo
```

An apply writes `.waybill-adapters.json` atomically after the adapter files.
The manifest contains no timestamp, uses deterministic key/path ordering, and
records the Waybill version plus each managed file digest. `doctor` classifies
managed files as `current`, `missing`, `stale`, or `modified`. Without a
manifest, an older installation can still identify an exact current file, but
a differing file is `modified` rather than reliably `stale`. An unsafe or
malformed manifest is reported as `invalid` and makes the check fail closed.

Codex is intentionally outside this lifecycle. Install its plugin using the
marketplace flow below; `init` never copies or manages the Codex plugin.

## Codex

This repository includes a repo-scoped plugin marketplace:

```text
.agents/plugins/marketplace.json
```

The marketplace exposes the Codex plugin at:

```text
adapters/codex/
```

To try it:

1. Open this repository in Codex.
2. Restart Codex if it was already running before this file existed.
3. Add the repository marketplace:

   ```bash
   codex plugin marketplace add .
   ```

4. Install the plugin:

   ```bash
   codex plugin add waybill@waybill-local
   ```

5. Confirm it is installed:

   ```bash
   codex plugin list
   ```

   Expected status:

   ```text
   waybill@waybill-local  installed, enabled
   ```

6. Start a new Codex thread.
7. Test the skill with:

   ```text
   /handoff import examples/claude-to-codex
   ```

The alias should behave the same way:

```text
/waybill import examples/claude-to-codex
```

Expected result: Codex reads the example bundle, checks the repository state,
summarizes the original task, and identifies the next recommended step without
applying `diff.patch`.

## Codex Plugin Directory Alternative

Instead of installing from the CLI, you can install from the plugin directory:

1. Open the plugin directory:

   ```text
   /plugins
   ```

2. Select the `Waybill Local` marketplace.
3. Install the `Waybill` plugin.
4. Start a new thread and run the same import smoke test.

## Claude Code

This repository includes project-scoped Claude Code skills:

```text
.claude/skills/handoff/SKILL.md
.claude/skills/waybill/SKILL.md
```

To try them:

1. Open this repository in Claude Code:

   ```bash
   claude
   ```

2. Invoke the primary command:

```text
/handoff import examples/codex-to-claude
```

3. Invoke the alias:

```text
/waybill import examples/codex-to-claude
```

Expected result: Claude Code reads the example bundle, checks the repository
state, summarizes the original task, and identifies the next recommended step
without applying `diff.patch`.

The older command instruction files are still provided in:

```text
adapters/claude-code/commands/
```

Use those files if your Claude Code setup still depends on `.claude/commands/`
style custom commands instead of skills.

## OpenCode

This repository includes project-scoped OpenCode commands and skills:

```text
.opencode/commands/handoff.md
.opencode/commands/waybill.md
.opencode/skills/handoff/SKILL.md
.opencode/skills/waybill/SKILL.md
```

To try them:

1. Open this repository in OpenCode:

   ```bash
   opencode
   ```

2. Invoke the primary command:

   ```text
   /handoff import examples/claude-to-codex
   ```

3. Invoke the alias:

   ```text
   /waybill import examples/claude-to-codex
   ```

Expected result: OpenCode reads the example bundle, checks the repository
state, summarizes the original task, and identifies the next recommended step
without applying `diff.patch`.

The reusable adapter files are available in:

```text
adapters/opencode/
```

## Cursor CLI

This repository includes project-scoped Cursor rules:

```text
.cursor/rules/
```

To smoke test them with Cursor CLI in read-only ask mode:

```bash
agent -p --trust --mode=ask "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

For scriptable output:

```bash
agent -p --trust --mode=ask --output-format json "handoff import examples/claude-to-codex. Do not modify files; only summarize."
```

Expected result: Cursor reads the example bundle, checks the repository state,
summarizes the original task, and does not automatically apply `diff.patch`.

Reusable adapter files are available in:

```text
adapters/cursor/
```

## Gemini CLI

This repository includes project-scoped Gemini CLI skills:

```text
.gemini/skills/
```

To smoke test them in read-only plan mode:

```bash
gemini --skip-trust --approval-mode plan -p "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

For scriptable output:

```bash
gemini --skip-trust --approval-mode plan --output-format json -p "handoff import examples/claude-to-codex. Do not modify files; only summarize."
```

Expected result: Gemini CLI reads the example bundle, checks the repository
state, summarizes the original task, and does not automatically apply
`diff.patch`.

Reusable adapter files are available in:

```text
adapters/gemini-cli/
```

## Python Support Package

The Python package provides the support CLI as a `waybill` command. It is useful
for validation, inspection, redaction, packing, rendering, and adapter
installation from outside a repository clone.

The package does not replace the agent-native `/handoff` and `/waybill`
commands. Those still come from the project adapter files installed into a
target repository.

After the package is published, install or run the support CLI with:

```bash
pipx install agent-waybill
waybill --help
```

or:

```bash
uvx agent-waybill --help
```

## Smoke Test

After installing the adapters you need, run the static repository validation:

```bash
python3 -m unittest discover -s tests -t . -v
python3 scripts/validate-waybill.py
python3 -m py_compile cli/waybill waybill_core/*.py scripts/*.py
scripts/sync-adapters.py --check
scripts/smoke-agents.sh --dry-run
python3 scripts/test-wheel-install.py
```

Install Claude Code, OpenCode, Cursor, and Gemini CLI project files into another
repository:

```bash
./cli/waybill init --target /path/to/repo --dry-run
./cli/waybill init --target /path/to/repo
./cli/waybill init --target /path/to/repo --json
```

Check the target repository installation:

```bash
./cli/waybill doctor --target /path/to/repo
./cli/waybill doctor --target /path/to/repo --json
```

The JSON reports use a top-level boolean `success` that is `true` exactly when
the command exits zero. JSON errors remain a single JSON object without prose
or traceback output.

Create a draft bundle:

```bash
./cli/waybill new --output .waybill --repo .
./cli/waybill new --output .waybill --repo . --json
```

Compare a bundle with the current repository state:

```bash
./cli/waybill verify-repo .waybill --repo .
./cli/waybill verify-repo .waybill --repo . --json
```

Verify delegation request/result correlation without changing either bundle:

```bash
./cli/waybill verify-pair /path/to/request /path/to/result
./cli/waybill verify-pair /path/to/request /path/to/result --json
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

Validate any generated bundle:

```bash
./cli/waybill validate .waybill
./cli/waybill validate .waybill --json
```

Inspect bundle metadata and validation status:

```bash
./cli/waybill inspect .waybill
./cli/waybill inspect .waybill --json
```

Create a redacted copy before sharing:

```bash
./cli/waybill redact .waybill --output .waybill-redacted
./cli/waybill redact .waybill --output .waybill-redacted --json
```

Redact, validate, and pack a shareable archive:

```bash
./cli/waybill share .waybill --check
./cli/waybill share .waybill --check --json
./cli/waybill share .waybill --output waybill.zip
./cli/waybill share .waybill --output waybill.zip --json
```

`share --check` does not require `--output` and performs no writes. Its findings
contain only finding type, relative path, match count, and blocking status; it
never prints matched secret content. Ordinary `share` still requires
`--output`.

Pack a validated bundle into a zip archive:

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

Then follow the manual end-to-end test plan in `TESTING.md`.
