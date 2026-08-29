# Waybill for Claude Code

This adapter provides Markdown command instructions for exporting and importing
Waybill Bundles in Claude Code.

The handoff entrypoint is a thin wrapper around the canonical workflow in
`skills/handoff/`. Shared references, bundle assets, and checker code are not
duplicated in this source directory.

Build a self-contained distribution, then install the project-scoped skills
without the Waybill CLI by copying:

```bash
python3 scripts/build-adapters.py
```

```text
dist/adapters/claude-code/skills/handoff/ -> .claude/skills/handoff/
dist/adapters/claude-code/skills/waybill/ -> .claude/skills/waybill/
```

The optional `waybill init --adapter claude-code` command provides a managed
copy with conflict preflight and drift diagnostics. Either path produces:

```text
.claude/skills/handoff/SKILL.md
.claude/skills/waybill/SKILL.md
```

Prefer those project-scoped skills. The files in `commands/` are kept as a
compatibility reference for setups that still use `.claude/commands/`.

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

## Generated Distribution

```text
commands/
  handoff-export.md
  handoff-import.md
skills/
  handoff/
    SKILL.md
    assets/
    references/
    scripts/
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

Basic export and import run entirely through the copied Skill without the
Waybill CLI or a Python package. If Python 3 is already available, the Skill can
optionally run its one bundled read-only checker.

## Safety

`.waybill/` may contain sensitive prompts, paths, diffs, logs, tokens, or
customer data. Keep it local unless the user explicitly chooses to share it.
