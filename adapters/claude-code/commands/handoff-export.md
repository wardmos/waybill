# Waybill Handoff Export

Use this command when the user asks for any of:

```text
/handoff export
/waybill export
handoff export
waybill export
export a waybill
```

Create a Waybill Bundle for the current unfinished task.

## Rules

- Generate agent-neutral content.
- Do not say that Claude Code must be the next agent.
- Distinguish facts from assumptions.
- Distinguish verified results from unverified claims.
- Use `.waybill/` as the default output directory.
- Require `WAYBILL.md` and `metadata.json`.
- Include `diff.patch`, `commands.log`, and `test-summary.md` when useful.
- Do not run tests unless the user explicitly asks.
- Do not upload or share bundle contents.

## Procedure

1. Identify the original user goal from the conversation.
2. Identify the current status, completed work, pending work, and blockers.
3. Inspect the repository with read-only commands when available:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
   - `git diff`
4. Create `.waybill/`.
5. Write `.waybill/WAYBILL.md` using `spec/waybill-template.md`.
6. Write `.waybill/metadata.json` following `spec/metadata.schema.json`.
7. Write `.waybill/diff.patch` from the current diff when git is available.
8. Write `.waybill/commands.log` with important commands from the conversation.
   Separate read-only inspection commands from bundle-writing actions. Do not
   claim every command was read-only if `.waybill/` was created or files were
   written.
9. Write `.waybill/test-summary.md` with passing, failing, and not-run checks.
10. Tell the user the bundle was created and remind them to review it for
    sensitive information.

## Metadata Guidance

Use these values when known:

- `schema_version`: `draft`
- `source_agent`: `claude-code`
- `created_at`: current UTC timestamp
- `repo_root`: `.`
- `git.branch`: current branch or `unknown`
- `git.base_ref`: known base ref or `unknown`
- `git.head_sha`: current HEAD SHA or `unknown`
- `git.dirty`: true when there are uncommitted changes

## Final Response

After export, summarize:

- Bundle path
- Files written
- Any missing recommended files
- Sensitive information warning
