# Waybill Gemini CLI Adapter

This adapter provides Gemini CLI workspace skills for exporting and importing
Waybill Bundles.

Gemini CLI discovers workspace skills from:

```text
.gemini/skills/<name>/SKILL.md
```

Gemini CLI can run interactively with `gemini`, or non-interactively with
`gemini -p`.

## Workflows

Prompt Gemini CLI with:

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
adapters/gemini-cli/skills/handoff/  -> .gemini/skills/handoff/
adapters/gemini-cli/skills/waybill/  -> .gemini/skills/waybill/
```

Or use the Waybill CLI:

```bash
./cli/waybill init --target /path/to/repo --adapter gemini-cli
```

## Gemini CLI Smoke Tests

Inspect an example bundle in read-only plan mode:

```bash
gemini --skip-trust --approval-mode plan --model gemini-3.1-flash-lite -p "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

Use JSON output for scriptable checks:

```bash
gemini --skip-trust --approval-mode plan --model gemini-3.1-flash-lite --output-format json -p "handoff import examples/claude-to-codex. Do not modify files; only summarize."
```

Expected behavior:

- Gemini CLI discovers the workspace `handoff` skill.
- Gemini CLI reads the Waybill Bundle.
- Gemini CLI verifies current repository state before acting.
- Gemini CLI summarizes the task, current status, risks, and next recommended
  step.
- Gemini CLI does not automatically apply `diff.patch`.

## Notes

- Exported bundles should set `metadata.json` `source_agent` to `gemini-cli`.
- `.waybill/` should remain ignored by git.
- Review `.waybill/` before sharing it outside the machine.
