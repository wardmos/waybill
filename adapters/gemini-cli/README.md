# Waybill Gemini CLI Adapter

This adapter provides Gemini CLI workspace skills for exporting and importing
Waybill Bundles.

The handoff entrypoint is a thin Gemini CLI wrapper around `skills/handoff/`.
Shared references, bundle assets, and checker code are maintained only in that
canonical Skill.

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

Build the standalone adapters, then copy the generated files into the target
repository:

```bash
python3 scripts/build-adapters.py
```

```text
dist/adapters/gemini-cli/skills/handoff/ -> .gemini/skills/handoff/
dist/adapters/gemini-cli/skills/waybill/ -> .gemini/skills/waybill/
```

The Waybill CLI is not required. If it is already available, use it as an
optional managed-copy convenience:

```bash
./cli/waybill init --target /path/to/repo --adapter gemini-cli
```

## Gemini CLI Smoke Tests

Inspect an example bundle in read-only plan mode:

```bash
gemini --skip-trust --approval-mode plan -p "handoff import examples/claude-to-codex. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
```

Use JSON output for scriptable checks:

```bash
gemini --skip-trust --approval-mode plan --output-format json -p "handoff import examples/claude-to-codex. Do not modify files; only summarize."
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
