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

Validate a bundle:

```bash
./cli/waybill validate .waybill
```

Inspect bundle metadata and validation status:

```bash
./cli/waybill inspect .waybill
```

The CLI is intentionally small and uses only the Python standard library.
It currently supports bundle validation and inspection.

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
- No secret redaction command yet.
- OpenCode support is file-based commands and skills; no OpenCode plugin hooks
  are required yet.

## Roadmap

- Claude Code and Codex handoff plugins, spec, templates, and examples.
- Thin CLI for validation, packing, rendering, and redaction.
- More adapters and compatibility fixtures.
