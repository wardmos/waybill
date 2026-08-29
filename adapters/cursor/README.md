# Waybill Cursor CLI Adapter

This adapter provides Cursor project rules for exporting and importing Waybill
Bundles from Cursor Agent and Cursor CLI.

The rules are thin Cursor wrappers around `skills/handoff/`. Shared workflow
references, bundle assets, and checker code are maintained only in the
canonical Skill.

Cursor supports project rules in:

```text
.cursor/rules/*.mdc
```

Cursor CLI loads the same project rules as the editor. It can run
interactively with `agent` or non-interactively with `agent -p`.

## Workflows

Prompt Cursor with:

```text
handoff
waybill
handoff export
waybill export
handoff import .waybill
waybill import .waybill
```

`handoff` is the primary workflow name and defaults to export when the
direction is omitted. `waybill` is an alias with the same behavior.

## Install In A Project

Build the standalone adapters, then copy the generated files into the target
repository:

```bash
python3 scripts/build-adapters.py
```

```text
dist/adapters/cursor/rules/handoff.mdc -> .cursor/rules/handoff.mdc
dist/adapters/cursor/rules/waybill.mdc -> .cursor/rules/waybill.mdc
dist/adapters/cursor/rules/waybill-handoff/ -> .cursor/rules/waybill-handoff/
```

The Waybill CLI is not required. If it is already available, use it as an
optional managed-copy convenience:

```bash
./cli/waybill init --target /path/to/repo --adapter cursor
```

## Cursor CLI Smoke Tests

Inspect an example bundle without editing files:

```bash
agent -p --trust --mode=ask "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

Use JSON output for scriptable checks:

```bash
agent -p --trust --mode=ask --output-format json "handoff import examples/claude-to-codex. Do not modify files; only summarize."
```

Expected behavior:

- Cursor reads the Waybill Bundle.
- Cursor verifies current repository state before acting.
- Cursor summarizes the task, current status, risks, and next recommended step.
- Cursor does not automatically apply `diff.patch`.

## Notes

- Exported bundles should set `metadata.json` `source_agent` to `cursor`.
- `.waybill/` should remain ignored by git.
- Review `.waybill/` before sharing it outside the machine.
