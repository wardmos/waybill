# Waybill for Codex

The repository root is the local Codex plugin for exporting and importing
Waybill Bundles. It uses the canonical `skills/handoff/` tree directly.

The optional standalone Codex distribution reuses that same canonical Skill;
this directory contains only Codex-specific documentation. Shared dispatch,
references, assets, and checker code remain under `skills/handoff/`.

Supported commands:

```text
/handoff
/waybill
/handoff export
/waybill export
/handoff import .waybill
/waybill import .waybill
```

`/handoff` is the primary command and defaults to export when the direction is
omitted. `/waybill` is an alias with the same behavior.

## Repository Plugin Files

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

To build the optional standalone layout under `dist/adapters/codex/`, run:

```bash
python3 scripts/build-adapters.py
```

## Behavior

Export creates a `.waybill/` directory in the current repository. Import reads an
existing `.waybill/` directory and grounds the next action in the current repo
state.

The plugin is intentionally prompt/Skill based. Basic export and import run
without the Waybill CLI or a programming language runtime. If Python 3 is
already available, the Skill can optionally run its one bundled read-only
checker.
