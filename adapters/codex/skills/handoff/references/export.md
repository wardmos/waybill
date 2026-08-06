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
- This workflow does not require the Waybill CLI.
- Never reuse stale or invent repository-state digests. Omit optional digest
  fields when no trusted helper can calculate them exactly.

## Procedure

1. Identify the original goal, completed work, pending work, and blockers from
   the conversation.
2. Inspect the repository with read-only commands when available:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
   - `git diff`
3. Create the bundle directory directly with the active agent's file-writing
   tools. When available, copy the five draft files from the
   [bundle template](../assets/bundle-template/) into it. Existing bundle files
   must not be overwritten without the user's approval.
4. Replace every `{{PLACEHOLDER}}` in the copied assets. Write `WAYBILL.md`
   using the exact headings described in the bundle-format reference when the
   assets are unavailable.
5. Write `metadata.json` using the bundle-format reference. Record the observed
   branch, HEAD, and dirty state. Omit optional digest fields unless exact values
   came from a trusted helper.
6. Write `diff.patch` from `git diff --binary HEAD --` when Git is available.
7. Write `commands.log` with important commands and outcomes. Separate
   read-only inspection from bundle-writing actions; do not claim every command
   was read-only after creating files.
8. Write `test-summary.md` with passing, failing, and not-run checks.
9. Re-read the finished files and perform the basic checks directly:
   - `WAYBILL.md` and `metadata.json` exist as regular files.
   - Every copied asset has no unresolved `{{PLACEHOLDER}}` values, and
     `metadata.json` is one JSON object.
   - `WAYBILL.md` contains every required heading for its handoff kind.
   - `source_agent`, branch, HEAD, and dirty state match the captured context.
   - Every declared artifact path stays inside the bundle.
   - Delegation IDs, roles, sources, and result status agree when applicable.
10. Re-inspect branch, HEAD, and status after the last bundle write. If the
    target repository changed during export, refresh the affected bundle facts
    and repeat the basic checks. Do not treat the bundle directory itself as a
    target-code change; warn when it is not ignored by Git.
11. Report the bundle path, files written, missing recommended files, whether
    repository digests were recorded, and the
    need to review the bundle for sensitive information.

## Optional Enhanced Verification

When a Python 3 runtime is already available, run the optional read-only
[bundled checker](../scripts/check_bundle.py) after the final write. Resolve the
linked script relative to this Skill and run
`python3 CHECKER BUNDLE --repo . --json`, replacing `CHECKER` and `BUNDLE` with
their actual paths. For a delegation result, add `--request REQUEST`. The
checker is bundled with the Skill and requires no Waybill CLI installation.

When the Waybill CLI is already available, it may provide further enhanced
verification; installing it is not part of this workflow. It can initialize a
digest-bearing draft with `waybill new`, and it can run `waybill validate`,
`waybill ready`, `waybill verify-repo`, and `waybill verify-pair`.

The absence of Python or the CLI never blocks a basic export. If an optional
checker or CLI command is run and finds a real bundle error, correct the bundle
and repeat all basic checks plus the optional command before claiming enhanced
verification.

For a delegation request, set a stable `request_id`, parent and child roles,
and make `source_agent` equal the parent. For a delegation result, set
`result_for` to the request ID, choose `result_status` from `completed`,
`partial`, or `blocked`, preserve both roles, and make `source_agent` equal the
child.
