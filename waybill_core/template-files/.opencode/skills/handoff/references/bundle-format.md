# Waybill Bundle Format

Read this reference before either exporting or importing a bundle.

## Files

The default bundle path is `.waybill/`.

Required files:

- `WAYBILL.md`
- `metadata.json`

Recommended files:

- `diff.patch`
- `commands.log`
- `test-summary.md`

Follow the repository copies of `spec/waybill-bundle.md`,
`spec/waybill-template.md`, `spec/delegation.md`, and
`spec/metadata.schema.json` when they are available.

For an ordinary handoff, `WAYBILL.md` uses these headings:

- `Original Goal`
- `Current Status`
- `User Constraints`
- `Repo State`
- `Changed Files`
- `Commands Run`
- `Test State`
- `Failed Attempts`
- `Current Hypothesis`
- `Next Recommended Step`
- `Risks / Unknowns`
- `Instructions For Next Agent`

A delegation request additionally records `Delegation Request`, `Child Agent
Task`, `Acceptance Criteria`, and `Return Instructions`. A delegation result
additionally records `Delegation Result`, `Work Completed`, `Parent Review
Notes`, and `Parent Next Step`.

## Handoff Metadata

Supported `metadata.json` handoff kinds:

- `handoff`: ordinary task transfer; this is the default when absent.
- `delegation_request`: a parent asks a child to perform a bounded subtask.
- `delegation_result`: a child returns work or findings for parent review.

Delegation metadata preserves correlation and roles:

- A request requires `request_id`, `parent_agent`, and `child_agent`; its
  top-level `source_agent` equals the parent.
- A result requires matching `result_for`, `result_status` (`completed`,
  `partial`, or `blocked`), `parent_agent`, and `child_agent`; its top-level
  `source_agent` equals the child.

Use this `metadata.json` shape for a current export:

```json
{
  "schema_version": "0.2",
  "source_agent": "<source-agent>",
  "created_at": "<current-UTC-timestamp>",
  "repo_root": ".",
  "git": {
    "branch": "main",
    "base_ref": "unknown",
    "head_sha": "<current-HEAD>",
    "dirty": true,
    "status_digest": "sha256:<exact-status-digest>",
    "repo_state_digest": "sha256:<exact-repository-state-digest>"
  },
  "artifacts": {
    "waybill": "WAYBILL.md",
    "diff": "diff.patch",
    "commands": "commands.log",
    "test_summary": "test-summary.md"
  }
}
```

The angle-bracket values describe required substitutions, not literal values.
Use `unknown` only for non-digest values that cannot be determined. A current
export must contain exact `git.status_digest` and `git.repo_state_digest`
values measured by `waybill new` or supplied by a trusted export context.
