# Waybill for Claude Code

This adapter provides Markdown command instructions for exporting and importing
Waybill Bundles in Claude Code.

The handoff entrypoint is a thin wrapper around the canonical workflow in
`skills/handoff/`. Its `references/` files are generated from that shared Skill.

`waybill init --adapter claude-code` installs project-scoped skills at:

```text
.claude/skills/handoff/SKILL.md
.claude/skills/waybill/SKILL.md
```

Prefer those project-scoped skills. The files in `commands/` are kept as a
compatibility reference for setups that still use `.claude/commands/`.

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
commands/
  handoff-export.md
  handoff-import.md
skills/
  handoff/
    SKILL.md
    references/
  waybill/
    SKILL.md
```

## Behavior

Export creates a local `.waybill/` directory with `WAYBILL.md` and
`metadata.json`, plus recommended artifacts when useful information is
available.

Import reads an existing Waybill Bundle, checks the current repository state,
and prepares Claude Code to continue the task. Import must not automatically
apply patches.

## Safety

`.waybill/` may contain sensitive prompts, paths, diffs, logs, tokens, or
customer data. Keep it local unless the user explicitly chooses to share it.
