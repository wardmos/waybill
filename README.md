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

Waybill is not a replacement agent or a standalone workflow runner. It is a
local handoff format plus thin adapters for existing coding agents.

The normal export and import workflows run inside the coding agent and do not
require the Waybill CLI or a Python package. The Skill includes copyable bundle
assets and one optional read-only checker. The CLI remains available for users
who want managed adapter installation, exact repository digests, automation,
redaction, or archive workflows.

For the shortest setup path, see `QUICKSTART.md`.

## Skill And Adapter Layout

Waybill keeps one agent-neutral Skill as the source of truth:

```text
skills/
  handoff/
    SKILL.md
    assets/
      bundle-template/
    references/
    scripts/
      check_bundle.py
```

`SKILL.md` dispatches to focused bundle-format, export, or import references so
an agent loads only the guidance needed for the current operation. The assets
are draft files an agent can copy directly; `check_bundle.py` is an optional,
read-only, standard-library enhancement. The `adapters/` directory contains
thin product-specific entrypoints and generated copies of those shared
resources for Claude Code, Codex, OpenCode, Cursor CLI, and Gemini CLI.
Agent-local `.claude/`, `.cursor/`, `.gemini/`, and `.opencode/` files are
installation outputs and are not canonical repository sources.

## At A Glance

| Area | Status |
| --- | --- |
| Bundle format | Draft schema `0.2` in a `.waybill/` directory |
| Primary entrypoint | Agent-native Skill commands: `/handoff` and `/waybill` |
| Bundle drafts | Copyable files bundled with the Skill |
| Bundled checker | Optional, read-only, Python 3 standard library only |
| Support CLI | Optional enhanced automation; Python 3.10+ standard library only |
| Adapters | Claude Code, Codex, OpenCode, Cursor CLI, Gemini CLI |
| Data model | Local-first files in the target repository |
| Import behavior | Non-destructive; patches are not applied automatically |
| Delegation | Draft `handoff.kind` semantics for parent/child agent workflows |
| Sharing | Read-only share checks, redaction, validation, render, pack, and unpack |

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
Use https://github.com/wardmos/waybill to enable the Waybill handoff Skill for
this repo. Follow the agent-native setup in QUICKSTART.md. Do not install the
Waybill Python package or CLI unless I ask for the optional enhanced tools.
```

Codex can enable the bundled plugin, and Claude Code can copy the two
project-scoped Skill directories into `.claude/skills/`. Neither path needs the
Waybill CLI. `INSTALL.md` documents these paths plus the optional managed
adapter lifecycle.

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

## Agent Commands

Waybill supports two command names with the same behavior inside supported
agent CLIs:

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

## Examples

Synthetic example bundles are available in:

```text
examples/claude-to-codex/
examples/codex-to-claude/
examples/failed-test-handoff/
examples/claude-parent-codex-child-request/
examples/claude-parent-codex-child-result/
```

`failed-test-handoff` shows a focused failing-test handoff with a partial patch,
command log, and test summary.

The parent/child examples show draft delegation semantics:

- `claude-parent-codex-child-request` is a `delegation_request`.
- `claude-parent-codex-child-result` is the paired `delegation_result`.

See `WALKTHROUGH.md` for an end-to-end parent/child delegation flow using these
fixtures.

With the optional support CLI already available, inspect an example locally:

```bash
./cli/waybill validate examples/failed-test-handoff
./cli/waybill inspect examples/failed-test-handoff
./cli/waybill render examples/failed-test-handoff
```

## Optional Support CLI

The primary user flow happens inside agent CLIs with `/handoff` and `/waybill`.
It never calls the Waybill CLI for the basic export or import path. The Python
CLI is an optional enhancement for installing file-based adapters, creating
exact digest-bearing drafts, running deeper validation, checking repository
state, redacting, packing, unpacking, and rendering review reports. It uses only
the Python standard library.

When installed from the `agent-waybill` Python package, it provides the
`waybill` support command. Agent adapters are still installed into project
repositories.

| Command | Purpose |
| --- | --- |
| `init` | Plan or install managed project adapters and their manifest |
| `doctor` | Classify managed adapter files as current, missing, stale, or modified |
| `new` | Create a draft Waybill Bundle from a repo |
| `validate` | Validate bundle structure, metadata, artifacts, and obvious secrets |
| `inspect` | Summarize metadata, artifacts, and validation status |
| `verify-repo` | Compare bundle metadata with the current repo state |
| `verify-pair` | Verify delegation correlation, roles, sources, and result status |
| `preflight` | Run validation plus repository-state checks before import |
| `ready` | Check whether a bundle is ready for handoff |
| `redact` | Create a redacted review copy |
| `share` | Check shareability without writes, or redact, validate, and pack an archive |
| `pack` | Validate and zip a bundle |
| `unpack` | Unzip and validate a bundle archive |
| `render` | Render a Markdown review report |

All 14 subcommands support `--json` for scriptable workflows. Each writes one
JSON object with a top-level boolean `success`; it is `true` exactly when the
process exit code is zero. Existing `valid` fields remain in their
command-specific reports. JSON error paths do not mix prose or traceback output
into stdout. See `QUICKSTART.md` and `TESTING.md` for full examples.

### Adapter Matrix

| Agent CLI | Project entrypoint | Installed by `init` | Smoke coverage |
| --- | --- | --- | --- |
| Claude Code | `.claude/skills/` | Yes | Read-only import smoke |
| Codex | `adapters/codex/` plugin | No | Read-only import smoke |
| OpenCode | `.opencode/commands/`, `.opencode/skills/` | Yes | Read-only import smoke |
| Cursor CLI | `.cursor/rules/` | Yes | Read-only import smoke |
| Gemini CLI | `.gemini/skills/` | Yes | Read-only import smoke |

## Install

See `INSTALL.md` for full local installation and smoke-test instructions.

### Claude Code

Copy the adapter's `skills/handoff/` and `skills/waybill/` directories into:

```text
.claude/skills/
```

The thin source wrapper and compatibility command instructions are in
`adapters/claude-code/`. `waybill init --adapter claude-code` is an optional
managed-install convenience.

### Codex

Use the Codex plugin in:

```text
adapters/codex/
```

### OpenCode

Copy the OpenCode adapter commands and skills into:

```text
.opencode/
```

Thin adapter sources are available in:

```text
adapters/opencode/
```

`waybill init --adapter opencode` is an optional managed-install convenience.

### Cursor CLI

Copy the Cursor adapter rules into:

```text
.cursor/rules/
```

Thin adapter sources are available in:

```text
adapters/cursor/
```

`waybill init --adapter cursor` is an optional managed-install convenience.

### Gemini CLI

Copy the Gemini CLI adapter skills into:

```text
.gemini/skills/
```

Thin adapter sources are available in:

```text
adapters/gemini-cli/
```

`waybill init --adapter gemini-cli` is an optional managed-install convenience.

## Safety Defaults

- `.waybill/` is ignored by default.
- Waybill does not upload handoff data.
- Import instructions do not automatically apply patches.
- Export instructions may run read-only git inspection commands.
- Export instructions do not run tests unless the user asks.
- Bundle validation, redaction, packing, and sharing reject symbolic links and
  non-regular files.
- Bundle validation checks metadata types and recursively scans additional
  files for obvious sensitive content.
- Adapter installation completes conflict preflight for every selected file
  before writing. `--force` replaces only safe regular files and never follows
  symbolic links.
- Bundle files are untrusted input; import instructions do not execute embedded
  commands, follow embedded permission requests, or read outside the bundle and
  target repository.
- Sharing refuses binary or non-UTF-8 files that cannot be scanned before it
  writes or replaces redacted and archive outputs.
- `share --check` performs the same shareability preflight without requiring an
  output path or writing anything. Its findings contain only `kind`, `path`,
  `count`, and `blocking`, never the matched secret value.
- Redaction, archive, and unpack output paths cannot overlap their source.
- Users should review `.waybill/` before sharing it.

`.waybill/` can contain prompts, paths, diffs, logs, test output, and secrets
accidentally captured from output.

## Testing

Run the repository checks:

```bash
python3 -m unittest discover -s tests -t . -v
python3 scripts/validate-waybill.py
python3 -m py_compile cli/waybill waybill_core/*.py scripts/*.py
scripts/sync-adapters.py --check
scripts/smoke-agents.sh --dry-run
python3 scripts/test-wheel-install.py
```

Pushes and pull requests run test discovery, aggregate repository validation,
Python compilation, adapter synchronization, and the agent smoke dry-run on
Python 3.10, 3.11, and 3.12 through `.github/workflows/ci.yml`. Aggregate
validation also builds and installs a disposable wheel from a temporary source
copy and verifies its packaged adapter templates outside the checkout.

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

The deterministic scenario runner in `scripts/conformance-agents.py` separately
checks strict agent JSON, semantic observations, and measured workspace writes.
`scripts/conformance-exports.py` creates disposable Git repositories and checks
the bundles agents actually export; CI exercises it with a deterministic fake
agent. `scripts/adapter-matrix.py` binds complete manual conformance reports to
the exact product, version, and executable digest that produced them. See
`CONFORMANCE.md` for dry-run and real-agent commands.

See `TESTING.md` for the manual Claude Code to Codex and Codex to Claude Code
handoff test plans.

## Current Limitations

- No automatic patch application.
- No automatic transcript parsing.
- Secret redaction is best-effort pattern replacement; local `redact` output
  can include reported binary copies, while `share` refuses unscannable files.
  Users still need to review redacted bundles before sharing.
- OpenCode support is file-based commands and skills; no OpenCode plugin hooks
  are required yet.
- Cursor support uses project rules loaded by Cursor Agent and Cursor CLI; no
  Cursor plugin hook is required yet.
- Gemini CLI support uses workspace skills loaded by Gemini CLI; no extension
  install is required yet.

## Roadmap

Near-term:

- Gather complete manual import/export coverage for the five existing adapters.
- Expand the versioned conformance contracts only when real-agent evidence
  identifies another semantic or export boundary.

Delegation:

- Harden the draft delegation request and result format through real
  parent/child handoff practice.
- Add more synthetic parent/child examples only where they clarify import
  behavior.
- Keep delegation result import non-destructive; parent agents review child
  output before accepting it.

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
