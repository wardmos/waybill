# Waybill OpenCode Adapter

This adapter provides native OpenCode commands and skills for exporting and
importing Waybill Bundles.

The commands and skills are thin OpenCode wrappers around `skills/handoff/`.
Shared references, bundle assets, and checker code are maintained only in the
canonical Skill.

OpenCode supports project-local custom commands in:

```text
.opencode/commands/
```

OpenCode supports project-local agent skills in:

```text
.opencode/skills/<name>/SKILL.md
```

## Commands

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

## Install In A Project

Build the standalone adapters, then copy the generated files into the target
repository:

```bash
python3 scripts/build-adapters.py
```

```text
dist/adapters/opencode/commands/handoff.md  -> .opencode/commands/handoff.md
dist/adapters/opencode/commands/waybill.md  -> .opencode/commands/waybill.md
dist/adapters/opencode/skills/handoff/      -> .opencode/skills/handoff/
dist/adapters/opencode/skills/waybill/      -> .opencode/skills/waybill/
```

Then start OpenCode from that repository:

```bash
opencode
```

The Waybill CLI is not required. If it is already available,
`waybill init --adapter opencode` is an optional managed-copy convenience.

Smoke test import with:

```text
/handoff import examples/claude-to-codex
```

Expected behavior:

- OpenCode reads the Waybill Bundle.
- OpenCode verifies current repository state before acting.
- OpenCode summarizes the task, current status, risks, and next recommended
  step.
- OpenCode does not automatically apply `diff.patch`.

## Notes

- Exported bundles should set `metadata.json` `source_agent` to `opencode`.
- `.waybill/` should remain ignored by git.
- Review `.waybill/` before sharing it outside the machine.
