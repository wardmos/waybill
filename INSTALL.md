# Install Waybill

Waybill ships as Markdown instructions for Claude Code, a local Codex plugin,
OpenCode commands and skills, Cursor project rules, Gemini CLI workspace
skills, copyable bundle assets, and one optional read-only checker. Basic
handoffs run inside those agents and do not require the Waybill CLI or a Python
package. A small standard-library CLI is available separately as an enhanced
automation layer.

For the shortest setup path, start with `QUICKSTART.md`. This document keeps
the fuller per-adapter details.

The only shared source of truth is `skills/handoff/`. Directories under
`adapters/` contain product-specific wrappers, commands, rules, and manifests,
but no copies of shared references, assets, or checker code. The support CLI
fans the canonical files out during installation. For a standalone copyable
distribution, build all adapters into the ignored `dist/` directory:

```bash
python3 scripts/build-adapters.py
```

The wheel also packages these two canonical source trees directly; it does not
need tracked fallback copies.

## Agent-Native Installation

The default installation unit is the adapter's Skill or plugin directory:

| Agent | Copy or enable |
| --- | --- |
| Claude Code | `dist/adapters/claude-code/skills/*` in `.claude/skills/` |
| Codex | the repository-root plugin |
| OpenCode | `dist/adapters/opencode/commands/*` and `skills/*` |
| Cursor | `dist/adapters/cursor/rules/*` in `.cursor/rules/` |
| Gemini CLI | `dist/adapters/gemini-cli/skills/*` in `.gemini/skills/` |

The generated directories are self-contained. Copying or enabling the relevant
one is enough for `/handoff` (which defaults to export) and `/handoff import`;
no Waybill CLI process runs behind the Skill. The source `adapters/`
directories are not standalone distributions. The per-agent sections below
give exact mappings.

## Optional Managed Adapter Lifecycle

When the support CLI is already available, `waybill init` can manage the
file-based Claude Code, OpenCode, Cursor CLI, and Gemini CLI adapters. This is a
convenience for conflict preflight, multi-adapter installation, deterministic
manifests, and drift diagnostics; it is not required by the Skills. Preview the
complete plan before writing:

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

The marketplace exposes this repository root as the Codex plugin, so it uses
the canonical `skills/handoff/` tree directly:

```text
./
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

## Codex Plugin UI Alternative

Instead of using Codex's command-line plugin management, you can install from
the plugin directory:

1. Open the plugin directory:

   ```text
   /plugins
   ```

2. Select the `Waybill Local` marketplace.
3. Install the `Waybill` plugin.
4. Start a new thread and run the same import smoke test.

## Claude Code

After installation, the target repository contains Claude Code skills at:

```text
.claude/skills/handoff/SKILL.md
.claude/skills/waybill/SKILL.md
```

Install without the Waybill CLI by first running
`python3 scripts/build-adapters.py`, then copying the generated Skill
directories after checking that the destinations will not overwrite local
changes:

```text
dist/adapters/claude-code/skills/handoff/ -> .claude/skills/handoff/
dist/adapters/claude-code/skills/waybill/ -> .claude/skills/waybill/
```

To try them:

1. Start Claude Code in the target repository:

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

If the optional support CLI is already available, this command performs the
same copy through the managed lifecycle:

```bash
./cli/waybill init --target . --adapter claude-code
```

The older command instruction files are still provided in:

```text
adapters/claude-code/commands/
```

Use those files if your Claude Code setup still depends on `.claude/commands/`
style custom commands instead of skills.

## OpenCode

After installation, the target repository contains OpenCode commands and
skills at:

```text
.opencode/commands/handoff.md
.opencode/commands/waybill.md
.opencode/skills/handoff/SKILL.md
.opencode/skills/waybill/SKILL.md
```

Install without the Waybill CLI by running
`python3 scripts/build-adapters.py` and copying:

```text
dist/adapters/opencode/commands/handoff.md -> .opencode/commands/handoff.md
dist/adapters/opencode/commands/waybill.md -> .opencode/commands/waybill.md
dist/adapters/opencode/skills/handoff/ -> .opencode/skills/handoff/
dist/adapters/opencode/skills/waybill/ -> .opencode/skills/waybill/
```

To try them:

1. Start OpenCode in the target repository:

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

The generated reusable adapter files are available in:

```text
dist/adapters/opencode/
```

Optional managed installation is available with
`./cli/waybill init --target . --adapter opencode`.

## Cursor CLI

After installation, the target repository contains Cursor rules under:

```text
.cursor/rules/
```

Install without the Waybill CLI by running
`python3 scripts/build-adapters.py` and copying:

```text
dist/adapters/cursor/rules/handoff.mdc -> .cursor/rules/handoff.mdc
dist/adapters/cursor/rules/waybill.mdc -> .cursor/rules/waybill.mdc
dist/adapters/cursor/rules/waybill-handoff/ -> .cursor/rules/waybill-handoff/
```

Then smoke test it in read-only ask mode:

```bash
agent -p --trust --mode=ask "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

For scriptable output:

```bash
agent -p --trust --mode=ask --output-format json "handoff import examples/claude-to-codex. Do not modify files; only summarize."
```

Expected result: Cursor reads the example bundle, checks the repository state,
summarizes the original task, and does not automatically apply `diff.patch`.

Generated reusable adapter files are available in:

```text
dist/adapters/cursor/
```

Optional managed installation is available with
`./cli/waybill init --target . --adapter cursor`.

## Gemini CLI

After installation, the target repository contains Gemini CLI skills under:

```text
.gemini/skills/
```

Install without the Waybill CLI by running
`python3 scripts/build-adapters.py` and copying:

```text
dist/adapters/gemini-cli/skills/handoff/ -> .gemini/skills/handoff/
dist/adapters/gemini-cli/skills/waybill/ -> .gemini/skills/waybill/
```

Then smoke test it in read-only plan mode:

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

Generated reusable adapter files are available in:

```text
dist/adapters/gemini-cli/
```

Optional managed installation is available with
`./cli/waybill init --target . --adapter gemini-cli`.

## Optional Python Support Package

The Python package provides the enhanced support CLI as a `waybill` command.
Install it only when you want managed adapter installation, exact digest-bearing
drafts, deeper validation, inspection, redaction, packing, or rendering from
outside a repository clone.

The package does not replace the agent-native `/handoff` and `/waybill`
commands and is not a runtime dependency of either workflow. Those commands
come from the project adapter files installed into a target repository.

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
