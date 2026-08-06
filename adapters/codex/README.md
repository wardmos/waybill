# Waybill for Codex

This adapter provides a Codex plugin for exporting and importing Waybill
Bundles.

Its handoff entrypoint is a thin Codex wrapper around `skills/handoff/`; the
plugin-local references, bundle assets, and checker are generated from that
canonical Skill.

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
    assets/
    references/
    scripts/
```

## Behavior

Export creates a `.waybill/` directory in the current repository. Import reads an
existing `.waybill/` directory and grounds the next action in the current repo
state.

The plugin is intentionally prompt/Skill based. Basic export and import run
without the Waybill CLI or a programming language runtime. If Python 3 is
already available, the Skill can optionally run its one bundled read-only
checker.
