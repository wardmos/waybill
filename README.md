# Waybill

Portable handover bundles for agents, starting with coding agents.

When an agent gets stuck, runs out of context, or needs to hand work to another
tool, Waybill gives the next agent a local, reviewable handoff bundle.

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

## At A Glance

| Area | Status |
| --- | --- |
| Bundle format | Draft `.waybill/` directory |
| CLI | Python standard library, no package manager install |
| Adapters | Claude Code, Codex, OpenCode, Cursor CLI, Gemini CLI |
| Data model | Local-first files in the target repository |
| Import behavior | Non-destructive; patches are not applied automatically |
| Sharing | Best-effort redaction, validation, render, pack, and unpack |

## When To Use Waybill

Use Waybill when:

- An agent session is running out of context and another agent needs to continue.
- You want to switch tools, models, or agent CLIs without losing task state.
- A human reviewer needs a compact summary of current progress, failed attempts,
  tests, diffs, and risks.
- You want a local handoff artifact that can be validated, redacted, rendered,
  packed, and shared intentionally.

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

Try one locally:

```bash
./cli/waybill validate examples/failed-test-handoff
./cli/waybill inspect examples/failed-test-handoff
./cli/waybill render examples/failed-test-handoff
```

## CLI

Common commands:

```bash
./cli/waybill init --target /path/to/repo
./cli/waybill doctor --target /path/to/repo
./cli/waybill new --output .waybill --repo .
./cli/waybill preflight .waybill --repo .
./cli/waybill ready .waybill --repo .
./cli/waybill validate .waybill
./cli/waybill inspect .waybill
./cli/waybill redact .waybill --output .waybill-redacted
./cli/waybill share .waybill --output waybill.zip
./cli/waybill render .waybill-redacted --output waybill-report.md
```

The CLI is intentionally small and uses only the Python standard library.

| Command | Purpose |
| --- | --- |
| `init` | Install file-based project adapters into a target repo |
| `doctor` | Check adapter installation and `.waybill/` ignore setup |
| `new` | Create a draft Waybill Bundle from a repo |
| `validate` | Validate bundle structure, metadata, artifacts, and obvious secrets |
| `inspect` | Summarize metadata, artifacts, and validation status |
| `verify-repo` | Compare bundle metadata with the current repo state |
| `preflight` | Run validation plus repository-state checks before import |
| `ready` | Check whether a bundle is ready for handoff |
| `redact` | Create a redacted review copy |
| `share` | Redact, validate, and pack a shareable archive |
| `pack` | Validate and zip a bundle |
| `unpack` | Unzip and validate a bundle archive |
| `render` | Render a Markdown review report |

Most commands support `--json` for scriptable workflows. See `QUICKSTART.md`
and `TESTING.md` for full command examples.

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

Near-term:

- Add more compatibility fixtures and documented walkthroughs for failed tests,
  code review, patch verification, and cross-agent handoff recovery.
- Strengthen conformance checks for agent-generated bundles.

Delegation:

- Add delegation request and result templates for parent/child agent workflows.
- Add parent/child examples such as Claude Code parent to Codex child, and Codex
  parent to Claude Code child, using synthetic repositories and non-destructive
  imports.
- Explore optional delegation metadata such as `handoff.kind`.

Orchestration Compatibility:

- Keep Waybill usable as an agent-neutral task envelope that future
  orchestrators can write and read.
- Keep Waybill out of the business of scheduling, running, or supervising
  agents.

Adapters:

- Add more adapters where the target CLI has a lightweight project instruction
  mechanism, after the handoff and delegation formats stay stable.

Non-goals for now:

- Automatic patch application.
- Automatic transcript parsing.
- Daemon behavior, cloud sync, and Web UI.
