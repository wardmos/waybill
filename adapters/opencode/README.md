# Waybill OpenCode Adapter

This adapter provides native OpenCode commands and skills for exporting and
importing Waybill Bundles.

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
/handoff export
/waybill export
/handoff import .waybill
/waybill import .waybill
```

`/handoff` is the primary command. `/waybill` is an alias.

## Install In A Project

Copy the adapter files into the target repository:

```text
adapters/opencode/commands/handoff.md  -> .opencode/commands/handoff.md
adapters/opencode/commands/waybill.md  -> .opencode/commands/waybill.md
adapters/opencode/skills/handoff/      -> .opencode/skills/handoff/
adapters/opencode/skills/waybill/      -> .opencode/skills/waybill/
```

Then start OpenCode from that repository:

```bash
opencode
```

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
