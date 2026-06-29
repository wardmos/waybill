# Waybill for Claude Code

This adapter provides Markdown command instructions for exporting and importing
Waybill Bundles in Claude Code.

The repository also includes project-scoped Claude Code skills at:

```text
.claude/skills/handoff/SKILL.md
.claude/skills/waybill/SKILL.md
```

Prefer those skills for current Claude Code versions. The files in
`commands/` are kept as a compatibility reference for setups that still use
`.claude/commands/`.

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
