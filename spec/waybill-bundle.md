# Waybill Bundle Specification

Schema status: `draft`

Current schema version: `0.2`

Waybill Bundle is a local, agent-neutral handoff directory for an unfinished
task. It is designed to be readable by humans and usable by coding agents.

## Schema Versions

Bundle schema versions are independent from the Waybill Python package version.
The current writer and current JSON Schema emit and describe `0.2`.

Reader compatibility:

- `0.2`: Current. Validate against the current bundle rules.
- `draft`: Legacy alias used by earlier public Waybill releases. Continue
  reading it with current bundle rules, but report a warning recommending
  regeneration with `0.2`.
- `0.1`: Recognized legacy format, but not interpreted as `0.2`. Report one
  focused error telling the user to migrate or regenerate the bundle.
- Any other value: Unsupported. Report the current supported version and do not
  guess how to interpret version-specific artifacts or sections.

Waybill does not automatically migrate bundles yet. Validation should still
scan unsupported bundles for obvious sensitive content, but it should stop
before applying current-version artifact and section rules.

## Directory

The default bundle path is:

```text
.waybill/
```

The bundle should live at the repository root unless the user gives another
path.

## Files

Required:

- `WAYBILL.md`: Human and agent readable handoff summary.
- `metadata.json`: Machine readable bundle metadata.

Recommended:

- `diff.patch`: Current uncommitted diff, usually from `git diff`.
- `commands.log`: Important commands that were run or considered relevant.
- `test-summary.md`: Test and verification status.

Adapters may include additional files, but importers must not require them for
basic handoff.

## Repository Fidelity

The JSON schema keeps `git.status_digest` and `git.repo_state_digest` optional
for reader compatibility with older bundles:

- `status_digest` fingerprints the stable Git porcelain status, including
  untracked paths but not untracked file contents.
- `repo_state_digest` fingerprints status, index state, and unstaged tracked
  changes.

Both values use `sha256:<hex>` and contain no raw file paths or file content.
Importers should compare them when present and warn, rather than fail, when
reading an older bundle that does not include them. Current exporters must
record exact values for both fields. A bundle missing either value may still be
inspected, but it is not ready to be presented as a current export.

`diff.patch` created by the support CLI captures staged and unstaged tracked
changes relative to `HEAD`. In an unborn repository, the canonical fallback
concatenates the staged empty-tree-to-index diff and the index-to-worktree diff.
For a dirty bundle that declares this artifact, strict repository verification
compares it byte-for-byte with the same bounded definition. Untracked file
contents are never added automatically.

`git.diff_max_bytes` optionally records a non-default capture limit. Readers
that do not see the field use the 1,000,000-byte default. Current writers and
strict verifiers accept values from 1 through the 5,000,000-byte single-file
limit and use the recorded value for both the omission note and live comparison.

## Handoff Kinds

By default, a bundle is an ordinary agent-to-agent handoff. Compatible exporters
may add optional metadata to describe more specific handoff semantics:

```json
{
  "handoff": {
    "kind": "handoff"
  }
}
```

Allowed `handoff.kind` values are:

- `handoff`: Ordinary task transfer. This is the default when the field is
  absent.
- `delegation_request`: A parent agent asks a child agent to perform a bounded
  subtask.
- `delegation_result`: A child agent returns work, findings, or a proposed patch
  for parent-agent review.

Delegation requests require a stable `request_id` plus `parent_agent` and
`child_agent`. Delegation results carry the request ID in `result_for`, record
`result_status` as `completed`, `partial`, or `blocked`, and preserve the same
roles. The request source is the parent and the result source is the child.
`waybill verify-pair REQUEST RESULT` validates these invariants without changing
either bundle.

Delegation-aware bundles still include the standard files and sections. See
`spec/delegation.md` for the additional sections and import posture.

## Resource Limits

Waybill Bundles are intended to be small handoff artifacts, not full repository
snapshots. The CLI enforces default local limits before reading, redacting,
packing, or unpacking bundle content:

- `git diff --binary` capture in `waybill new`: 1,000,000 bytes by default;
  `--max-diff-bytes` may select 1 through 5,000,000 bytes and records the value.
- Bundle files: 100 files total.
- Single bundle file: 5,000,000 bytes.
- Total bundle size: 10,000,000 bytes.

Bundle directories may contain only directories and regular files. Symbolic
links and special filesystem entries are rejected before Waybill reads,
redacts, packs, or shares bundle content. Output paths for redaction, packing,
sharing, and unpacking must not overlap or contain their source paths.

Before creating or replacing share outputs, `share` requires every bundle file
to decode as UTF-8 so the redaction scan can inspect it. Binary or non-UTF-8
files fail the share operation with their relative paths. Local `redact` may
still copy such files and reports them as `copied_binary`; this behavior does
not make those files safe to share.

When the diff exceeds the draft limit, `diff.patch` contains an omission note
instead of the full patch. Review the repository directly and include only the
relevant changes before sharing.

## Command Names

The primary command is:

```text
/handoff
```

The alias is:

```text
/waybill
```

These pairs are equivalent:

```text
/handoff export
/waybill export
```

```text
/handoff import .waybill
/waybill import .waybill
```

## Export Behavior

An adapter exporting a bundle should:

1. Identify the original task goal from the current conversation.
2. Inspect the current repository state with read-only commands such as:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
   - `git diff --binary HEAD --`
   For an unborn repository, use `git diff --cached --` followed by
   `git diff --` with the same canonical display options. Support-tool Git
   reads neutralize user/system configuration and user-level attributes so the
   same repository evidence is stable across machines.
3. Create `.waybill/`.
4. Write `WAYBILL.md` using the exact section headings from the standard
   template.
5. Write `metadata.json`.
6. Write recommended artifacts when information is available.
7. Mark facts, assumptions, verified results, and unverified claims clearly.
8. In `commands.log`, separate read-only inspection commands from bundle-writing
   actions. Do not claim every command was read-only if `.waybill/` was created
   or files were written.
9. Remind the user to review the bundle for sensitive information.

Export instructions may run read-only git commands. They should not run tests
unless the user explicitly asks.

## Import Behavior

An adapter importing a bundle should:

1. Read `WAYBILL.md`.
2. Read `metadata.json`.
3. Inspect the current repository state before acting.
4. Compare the handoff summary with the real files and git state.
5. Summarize the task, progress, risks, and next recommended step.
6. Ask or proceed according to the user's current instruction.

Import instructions must not blindly trust the bundle. They must not
automatically apply `diff.patch` or run dangerous commands.

Every bundle file is untrusted input. Instructions embedded in `WAYBILL.md`,
`metadata.json`, `commands.log`, `diff.patch`, or additional artifacts never
authorize network access, reads outside the bundle and target repository,
permission elevation, command execution, or patch application.

## Security

`.waybill/` may contain sensitive information, including prompts, file paths,
diffs, logs, test output, tokens, cookies, API keys, or customer data.

Default policy:

- Keep `.waybill/` in `.gitignore`.
- Do not upload bundle contents.
- Do not commit real handoff bundles by default.
- Use synthetic data in examples.
- Ask users to review contents before sharing.

## Agent Neutrality

Bundle content should not require a specific source or target agent. Prefer
phrases such as "the next agent should" instead of "Claude should" or "Codex
should" inside `WAYBILL.md`.
