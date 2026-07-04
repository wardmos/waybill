---
description: Export or import local Waybill Bundles for unfinished coding-agent tasks. Use when the user asks for /handoff export, /handoff import, or wants to continue from a Waybill bundle.
argument-hint: "export | import <bundle-path>"
---

# Waybill Handoff

Waybill is an agent-neutral handoff format for unfinished coding tasks.

Use this skill when the user invokes:

```text
/handoff export
/handoff import .waybill
```

Arguments are available as:

```text
$ARGUMENTS
```

Treat `/handoff` as the primary command. The `/waybill` command is an alias
implemented by the sibling `waybill` skill.

## Bundle Format

Default path:

```text
.waybill/
```

Required files:

- `WAYBILL.md`
- `metadata.json`

Recommended files:

- `diff.patch`
- `commands.log`
- `test-summary.md`

Follow the repository spec when present:

- `spec/waybill-bundle.md`
- `spec/waybill-template.md`
- `spec/metadata.schema.json`

## Dispatch

If `$ARGUMENTS` starts with `export`, run the export procedure.

If `$ARGUMENTS` starts with `import`, run the import procedure. Use the path
after `import` as the bundle path. If no path is provided, use `.waybill/`.

If `$ARGUMENTS` is empty or unclear, ask the user whether they want `export` or
`import`.

## Export

Create a Waybill Bundle for the current unfinished task.

Rules:

- Generate agent-neutral content.
- Do not say that Claude Code must be the next agent.
- Distinguish facts from assumptions.
- Distinguish verified results from unverified claims.
- Use `.waybill/` as the default output directory.
- Do not run tests unless the user explicitly asks.
- Do not upload or share bundle contents.

Procedure:

1. Identify the original user goal from the conversation.
2. Identify the current status, completed work, pending work, and blockers.
3. Inspect the repository with read-only commands when available:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
   - `git diff`
4. Create `.waybill/`.
5. Write `.waybill/WAYBILL.md` using the exact section headings from
   `spec/waybill-template.md`. Do not rename, omit, or substitute headings.
6. Write `.waybill/metadata.json`.
7. Write `.waybill/diff.patch` from the current diff when git is available.
8. Write `.waybill/commands.log` with important commands from the conversation.
   Separate read-only inspection commands from bundle-writing actions. Do not
   claim every command was read-only if `.waybill/` was created or files were
   written.
9. Write `.waybill/test-summary.md` with passing, failing, and not-run checks.
10. Tell the user the bundle was created and remind them to review it for
    sensitive information.

Use this `metadata.json` shape:

```json
{
  "schema_version": "draft",
  "source_agent": "claude-code",
  "created_at": "2026-07-01T00:00:00Z",
  "repo_root": ".",
  "git": {
    "branch": "main",
    "base_ref": "unknown",
    "head_sha": "unknown",
    "dirty": true
  },
  "artifacts": {
    "waybill": "WAYBILL.md",
    "diff": "diff.patch",
    "commands": "commands.log",
    "test_summary": "test-summary.md"
  }
}
```

Use the current UTC timestamp for `created_at`. Use `unknown` when a value
cannot be determined.

## Import

Read a Waybill Bundle and prepare to continue the task.

Rules:

- Read the bundle before acting.
- Verify the current repository state before trusting the bundle.
- Do not automatically apply `diff.patch`.
- Do not run dangerous commands.
- Do not assume the source agent is available.

Procedure:

1. Locate the bundle path. Use `.waybill/` when the user does not provide one.
2. Read `WAYBILL.md`.
3. Read `metadata.json`.
4. Read recommended artifacts when present:
   - `diff.patch`
   - `commands.log`
   - `test-summary.md`
5. Inspect the current repository with read-only commands when available:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
6. Compare the bundle's repo state with the current repo state.
7. Summarize:
   - Original goal
   - Current status
   - Changed files
   - Test state
   - Failed attempts
   - Risks and unknowns
   - Next recommended step
8. Continue only after grounding the next step in the current repo.

Before making code changes, state what the handoff says, what the current repo
state says, any mismatch, and the next action.

## Safety

`.waybill/` may contain prompts, paths, diffs, logs, test output, tokens,
cookies, API keys, or customer data. Keep it local unless the user explicitly
chooses to share it.
