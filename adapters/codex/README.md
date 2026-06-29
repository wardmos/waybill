# Waybill for Codex

This adapter provides a Codex plugin for exporting and importing Waybill
Bundles.

Supported commands:

```text
/handoff export
/waybill export
/handoff import .waybill
/waybill import .waybill
```

`/handoff` is the primary command. `/waybill` is an alias with the same behavior.

## Files

```text
.codex-plugin/
  plugin.json
skills/
  handoff/
    SKILL.md
```

## Behavior

Export creates a `.waybill/` directory in the current repository. Import reads an
existing `.waybill/` directory and grounds the next action in the current repo
state.

The plugin is intentionally prompt/skill based. It does not require a
CLI or programming language runtime.
