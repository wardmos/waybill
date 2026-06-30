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

Waybill keeps handoffs agent-neutral, local-first, and portable across coding agents.
Waybill started with Claude Code and Codex. The current adapter set also
includes OpenCode.

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

## CLI

Install project-local Claude Code and OpenCode adapter files into another repo:

```bash
./cli/waybill init --target /path/to/repo
```

Check a target repo's adapter installation:

```bash
./cli/waybill doctor --target /path/to/repo
```

Create a draft bundle from the current repo:

```bash
./cli/waybill new --output .waybill --repo .
```

Compare bundle metadata with the current repo:

```bash
./cli/waybill verify-repo .waybill --repo .
```

Validate a bundle:

```bash
./cli/waybill validate .waybill
```

Inspect bundle metadata and validation status:

```bash
./cli/waybill inspect .waybill
```

Create a redacted copy for review before sharing:

```bash
./cli/waybill redact .waybill --output .waybill-redacted
```

Pack a validated bundle into a zip archive:

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

The CLI is intentionally small and uses only the Python standard library.
It currently supports adapter initialization checks, draft bundle scaffolding,
repository-state verification, bundle validation, inspection, redacted copies,
Markdown rendering, zip packing, and zip unpacking.

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

See `TESTING.md` for the manual Claude Code to Codex and Codex to Claude Code
handoff test plans.

## Current Limitations

- No automatic patch application.
- No automatic transcript parsing.
- Secret redaction is best-effort pattern replacement; users still need to
  review redacted bundles before sharing.
- OpenCode support is file-based commands and skills; no OpenCode plugin hooks
  are required yet.

## Roadmap

- Claude Code and Codex handoff plugins, spec, templates, and examples.
- Thin CLI for validation, packing, rendering, and redaction.
- More adapters and compatibility fixtures.
