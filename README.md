# Waybill

Portable handover bundles for agents, starting with coding agents.

Export an unfinished task from Claude Code:

```text
/handoff export
```

Continue it in Codex:

```text
/handoff import .waybill
```

Waybill helps continue unfinished coding work across different agents. Native
`resume` commands usually continue sessions inside one agent CLI.
Waybill keeps handoffs agent-neutral and portable across coding agents.
Waybill started with Claude Code and Codex. The current adapter set also
includes OpenCode, Cursor CLI, and Gemini CLI.

For the shortest setup path, see `QUICKSTART.md`.

## Validated Handoffs

Waybill has been exercised with real cross-agent handoffs in both directions:

- Claude Code exported an unfinished coding task, and Codex imported the bundle,
  verified repository state, finished the focused fix, and ran tests.
- Codex exported an unfinished coding task, and Claude Code imported the bundle,
  verified repository state, finished the focused fix, and ran tests.

Import remains non-destructive: the next agent reads the bundle and checks the
current repository state before deciding what to do.

## Agent-Assisted Install

Give your coding agent this repository URL and ask:

```text
Use https://github.com/wardmos/waybill to install Waybill adapters into this
repo. Follow QUICKSTART.md, then run the doctor check.
```

The agent should run:

```bash
./cli/waybill init --target /path/to/your/repo
./cli/waybill doctor --target /path/to/your/repo
```

`init` installs file-based project adapters for Claude Code, OpenCode, Cursor,
and Gemini CLI. Codex uses the local plugin marketplace described in
`INSTALL.md`.

## What Waybill Creates

A Waybill Bundle is a local directory in the current repository:

```text
.waybill/
  WAYBILL.md
  metadata.json
  diff.patch
  commands.log
  test-summary.md
```

Required files:

- `WAYBILL.md`
- `metadata.json`

Recommended files:

- `diff.patch`
- `commands.log`
- `test-summary.md`

## Examples

Synthetic example bundles are available in:

```text
examples/claude-to-codex/
examples/codex-to-claude/
examples/failed-test-handoff/
```

`failed-test-handoff` shows a focused failing-test handoff with a partial patch,
command log, and test summary.

## CLI

Install project-local Claude Code, OpenCode, Cursor, and Gemini CLI adapter
files into another repo:

```bash
./cli/waybill init --target /path/to/repo
./cli/waybill init --target /path/to/repo --json
```

Check a target repo's adapter installation:

```bash
./cli/waybill doctor --target /path/to/repo
./cli/waybill doctor --target /path/to/repo --json
```

Create a draft bundle from the current repo:

```bash
./cli/waybill new --output .waybill --repo .
./cli/waybill new --output .waybill --repo . --json
```

Compare bundle metadata with the current repo:

```bash
./cli/waybill verify-repo .waybill --repo .
./cli/waybill verify-repo .waybill --repo . --json
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

Validate a bundle:

```bash
./cli/waybill validate .waybill
./cli/waybill validate .waybill --json
```

Inspect bundle metadata and validation status:

```bash
./cli/waybill inspect .waybill
./cli/waybill inspect .waybill --json
```

Create a redacted copy for review before sharing:

```bash
./cli/waybill redact .waybill --output .waybill-redacted
./cli/waybill redact .waybill --output .waybill-redacted --json
```

Redact, validate, and pack a shareable archive:

```bash
./cli/waybill share .waybill --output waybill.zip
./cli/waybill share .waybill --output waybill.zip --json
```

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

The CLI is intentionally small and uses only the Python standard library.
It currently supports adapter initialization checks, draft bundle scaffolding,
import preflight checks, repository-state verification, bundle validation,
export readiness checks, inspection, redacted copies, shareable archive
preparation, Markdown rendering, zip packing, and zip unpacking.

### Adapter Matrix

| Agent CLI | Project entrypoint | Installed by `init` | Smoke coverage |
| --- | --- | --- | --- |
| Claude Code | `.claude/skills/` | Yes | Read-only import smoke |
| Codex | `adapters/codex/` plugin | No | Read-only import smoke |
| OpenCode | `.opencode/commands/`, `.opencode/skills/` | Yes | Read-only import smoke |
| Cursor CLI | `.cursor/rules/` | Yes | Read-only import smoke |
| Gemini CLI | `.gemini/skills/` | Yes | Read-only import smoke |

## Commands

Waybill supports two command names with the same behavior:

```text
/handoff export
/waybill export
```

```text
/handoff import .waybill
/waybill import .waybill
```

`/handoff` is the primary command because it describes the user action. `/waybill`
is an alias for users who think in terms of the project name.

## Install

See `INSTALL.md` for full local installation and smoke-test instructions.

### Claude Code

Use the project-scoped Claude Code skills in:

```text
.claude/skills/
```

Compatibility command instructions are also available in
`adapters/claude-code/commands/`.

### Codex

Use the Codex plugin in:

```text
adapters/codex/
```

### OpenCode

Use the OpenCode project commands and skills in:

```text
.opencode/
```

Reusable adapter files are available in:

```text
adapters/opencode/
```

### Cursor CLI

Use the Cursor project rules in:

```text
.cursor/rules/
```

Reusable adapter files are available in:

```text
adapters/cursor/
```

### Gemini CLI

Use the Gemini CLI workspace skills in:

```text
.gemini/skills/
```

Reusable adapter files are available in:

```text
adapters/gemini-cli/
```

## Safety Defaults

- `.waybill/` is ignored by default.
- Waybill does not upload handoff data.
- Import instructions do not automatically apply patches.
- Export instructions may run read-only git inspection commands.
- Export instructions do not run tests unless the user asks.
- Users should review `.waybill/` before sharing it.

`.waybill/` can contain prompts, paths, diffs, logs, test output, and secrets
accidentally captured from output.

## Testing

Run the repository checks:

```bash
python3 scripts/validate-waybill.py
```

Run repeatable local agent smoke tests when the relevant CLIs are installed:

```bash
scripts/smoke-agents.sh --tool codex
scripts/smoke-agents.sh --tool opencode
scripts/smoke-agents.sh --tool cursor
scripts/smoke-agents.sh --tool gemini
scripts/smoke-agents.sh --tool claude
```

Use `scripts/smoke-agents.sh --dry-run` to print the exact commands without
calling any agent model.

See `TESTING.md` for the manual Claude Code to Codex and Codex to Claude Code
handoff test plans.

## Current Limitations

- No automatic patch application.
- No automatic transcript parsing.
- Secret redaction is best-effort pattern replacement; users still need to
  review redacted bundles before sharing.
- OpenCode support is file-based commands and skills; no OpenCode plugin hooks
  are required yet.
- Cursor support uses project rules loaded by Cursor Agent and Cursor CLI; no
  Cursor plugin hook is required yet.
- Gemini CLI support uses workspace skills loaded by Gemini CLI; no extension
  install is required yet.

## Roadmap

- Keep the draft bundle format small and stable while real handoffs exercise it.
- Add more compatibility fixtures and documented cross-agent walkthroughs.
- Add more adapters where the target CLI has a lightweight project instruction
  mechanism.
- Keep automatic patch application, transcript parsing, daemon behavior, cloud
  sync, and Web UI out of scope until the handoff format has more usage.
