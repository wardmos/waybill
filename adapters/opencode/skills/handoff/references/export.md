# Export Workflow

Create a Waybill Bundle for the current unfinished task. Use the
`source_agent` supplied by the active adapter wrapper or the actual current
agent identity selected by the canonical skill.

## Rules

- Generate agent-neutral content; do not require the next agent to use the same
  product.
- Separate facts from assumptions and verified results from unverified claims.
- Use `.waybill/` unless the user specifies another output path.
- Do not run tests unless the user explicitly asks.
- Do not upload or share bundle contents.
- Never omit, reuse stale, or invent repository-state digests.

## Procedure

1. Identify the original goal, completed work, pending work, and blockers from
   the conversation.
2. Inspect the repository with read-only commands when available:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
   - `git diff`
3. Initialize the bundle with
   `waybill new --output .waybill --repo . --source-agent SOURCE_AGENT` when the
   CLI is available. Replace `SOURCE_AGENT` with the adapter identity and
   preserve the measured `status_digest` and `repo_state_digest` while replacing
   draft content. If neither the CLI nor a trusted export context can supply
   exact digests, stop and report that the export is not ready.
4. Write `WAYBILL.md` using the exact headings described in the bundle-format
   reference and the repository templates when present.
5. Write `metadata.json` using the bundle-format reference.
6. Write `diff.patch` from the current diff when Git is available.
7. Write `commands.log` with important commands and outcomes. Separate
   read-only inspection from bundle-writing actions; do not claim every command
   was read-only after creating files.
8. Write `test-summary.md` with passing, failing, and not-run checks.
9. Finish every bundle write, then run these final gates in order:
   - `waybill validate .waybill`
   - `waybill ready .waybill --repo .`
   - `waybill verify-repo .waybill --repo .`
   - For a `delegation_result`, also run
     `waybill verify-pair REQUEST .waybill`, replacing `REQUEST` with the
     original request bundle path.
10. Do not modify `.waybill/` after final validation begins. If a gate requires
    a correction, make it and restart the complete gate sequence after the new
    final write. Claim success only when every required gate passes.
11. Report the bundle path, files written, missing recommended files, and the
    need to review the bundle for sensitive information.

For a delegation request, set a stable `request_id`, parent and child roles,
and make `source_agent` equal the parent. For a delegation result, set
`result_for` to the request ID, choose `result_status` from `completed`,
`partial`, or `blocked`, preserve both roles, and make `source_agent` equal the
child.
