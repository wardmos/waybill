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
- Current exports must record exact `git.status_digest` and
  `git.repo_state_digest` values. Never omit, reuse stale, or invent them.

## Procedure

1. Identify the original user goal from the conversation.
2. Identify the current status, completed work, pending work, and blockers.
3. Inspect the repository with read-only commands when available:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
   - `git diff`
4. Create `.waybill/`. When the Waybill CLI is available, initialize it with
   `waybill new --output .waybill --repo . --source-agent claude-code` and
   preserve its measured `status_digest` and `repo_state_digest` while replacing
   draft content. Otherwise, use exact digest values supplied by a trusted
   export context; if neither source is available, stop and report the export
   as not ready.
5. Write `.waybill/WAYBILL.md` using the exact section headings from
   `spec/waybill-template.md`. Do not rename, omit, or substitute headings.
6. Write `.waybill/metadata.json` following `spec/metadata.schema.json`.
7. Write `.waybill/diff.patch` from the current diff when git is available.
8. Write `.waybill/commands.log` with important commands from the conversation.
   Separate read-only inspection commands from bundle-writing actions. Do not
   claim every command was read-only if `.waybill/` was created or files were
   written.
9. Write `.waybill/test-summary.md` with passing, failing, and not-run checks.
10. Finish every bundle write, then run these final gates in order:
    - `waybill validate .waybill`
    - `waybill ready .waybill --repo .`
    - `waybill verify-repo .waybill --repo .`
    - For a `delegation_result`, also run
      `waybill verify-pair REQUEST .waybill`, replacing `REQUEST` with the
      original request bundle path.
    Do not modify `.waybill/` after final validation begins. If a gate requires
    a fix, make the fix and restart the complete gate sequence after the new
    final write. Do not claim a successful export unless every required gate
    passes.
11. Tell the user the bundle was created and remind them to review it for
    sensitive information.

## Metadata Guidance

Use these values when known:

- `schema_version`: `0.2`
- `source_agent`: `claude-code`
- `created_at`: current UTC timestamp
- `repo_root`: `.`
- `handoff.kind`: omit for ordinary handoffs, or use `delegation_request` /
  `delegation_result` when the user is explicitly delegating a bounded child
  task or returning a child-agent result
- For `delegation_request`, set a stable `handoff.request_id`, set
  `parent_agent` and `child_agent`, and make `source_agent` equal the parent.
- For `delegation_result`, set `handoff.result_for` to the request ID, set
  `result_status` to `completed`, `partial`, or `blocked`, preserve
  `parent_agent` and `child_agent`, and make `source_agent` equal the child.
- `git.branch`: current branch or `unknown`
- `git.base_ref`: known base ref or `unknown`
- `git.head_sha`: current HEAD SHA or `unknown`
- `git.dirty`: true when there are uncommitted changes
- `git.status_digest`: exact current status digest measured by `waybill new` or
  supplied by a trusted export context; never `unknown`
- `git.repo_state_digest`: exact current tracked-state digest measured by
  `waybill new` or supplied by a trusted export context; never `unknown`

## Final Response

After export, summarize:

- Bundle path
- Files written
- Any missing recommended files
- Sensitive information warning
