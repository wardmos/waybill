# Waybill Cursor CLI Adapter

This adapter provides Cursor project rules for exporting and importing Waybill
Bundles from Cursor Agent and Cursor CLI.

Cursor supports project rules in:

```text
.cursor/rules/*.mdc
```

Cursor CLI loads the same project rules as the editor. It can run
interactively with `agent` or non-interactively with `agent -p`.

## Workflows

Prompt Cursor with:

```text
handoff export
waybill export
handoff import .waybill
waybill import .waybill
```

`handoff` is the primary workflow name. `waybill` is an alias.

## Install In A Project

Copy the adapter files into the target repository:

```text
adapters/cursor/rules/handoff.mdc  -> .cursor/rules/handoff.mdc
adapters/cursor/rules/waybill.mdc  -> .cursor/rules/waybill.mdc
```

Or use the Waybill CLI:

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
