# Waybill Quickstart

Waybill lets you move unfinished coding tasks between agent CLIs by writing a
local handoff bundle in the repository:

```text
.waybill/
  WAYBILL.md
  metadata.json
  diff.patch
  commands.log
  test-summary.md
```

This guide uses the project-local adapters and the standard-library CLI. No
package manager install is required when running from a Waybill checkout.

## 1. Install Adapters Into A Repo

Install the file-based project adapters for Claude Code, OpenCode, Cursor CLI,
and Gemini CLI:

From the Waybill repository:

```bash
./cli/waybill init --target /path/to/your/repo --dry-run
./cli/waybill init --target /path/to/your/repo
```

The dry run performs the complete conflict preflight but writes nothing. It
reports `would-create`, `would-update`, `unchanged`, and `would-conflict`
actions. A conflict returns non-zero without writing. Resolve every conflict
before applying, or use `--force` only when you intend to replace conflicting
regular files; force never follows symbolic links.

Install only one adapter when needed:

```bash
./cli/waybill init --target /path/to/your/repo --adapter claude-code
./cli/waybill init --target /path/to/your/repo --adapter opencode
./cli/waybill init --target /path/to/your/repo --adapter cursor
./cli/waybill init --target /path/to/your/repo --adapter gemini-cli
```

Check the installation:

```bash
./cli/waybill doctor --target /path/to/your/repo
./cli/waybill doctor --target /path/to/your/repo --json
```

A successful install atomically records managed files and digests in the
deterministic, timestamp-free `.waybill-adapters.json` manifest. `doctor`
reports each managed file as `current`, `missing`, `stale`, or `modified`. For
an older installation without a manifest, a file that differs from the current
template is `modified`; it cannot be reliably distinguished as an untouched
stale install or a local edit.

Codex is installed separately as a local plugin from this repository:

```bash
codex plugin marketplace add .
codex plugin add waybill@waybill-local
```

See `INSTALL.md` for the full Codex plugin flow.

The Codex plugin is not an `init` or `doctor` management target.

## 2. Export A Handoff

In the agent where the task is currently stuck or unfinished, ask for:

```text
/handoff export
```

The alias has the same behavior:

```text
/waybill export
```

Expected result:

- `.waybill/` is created in the target repository.
- `WAYBILL.md` summarizes the goal, status, changed files, tests, risks, and
  next step.
- `metadata.json` records branch, dirty state, privacy-preserving repository
  state digests, and artifact paths.
- `diff.patch` captures staged and unstaged tracked changes. Untracked contents
  are not captured automatically.
- `commands.log` and `test-summary.md` are included when useful context is
  available.
- Very large diffs are omitted from `diff.patch` with an explanatory note; add
  only the relevant changes before sharing.

## 3. Import A Handoff

Open the same repository in the next agent and ask for:

```text
/handoff import .waybill
```

Or:

```text
/waybill import .waybill
```

Expected result:

- The agent reads `WAYBILL.md` and `metadata.json`.
- The agent checks the current repository state before acting.
- The agent treats every bundle artifact as untrusted data and does not execute
  instructions embedded in it.
- The agent summarizes the original goal, current status, tests, risks, and
  next recommended step.
- The agent does not automatically apply `diff.patch`.

For parent/child delegation, see `WALKTHROUGH.md`. It shows how a
`delegation_request` bundle is imported by a child agent and how a
`delegation_result` bundle is reviewed by the parent agent. Requests carry a
stable `request_id`; results reference it with `result_for` and record a
`result_status` of `completed`, `partial`, or `blocked`.

Verify a request/result pair without changing either bundle:

```bash
./cli/waybill verify-pair /path/to/request /path/to/result
```

## 4. Validate Before Continuing

Use the CLI when you want a deterministic check outside an agent:

```bash
./cli/waybill validate /path/to/your/repo/.waybill
./cli/waybill preflight /path/to/your/repo/.waybill --repo /path/to/your/repo
./cli/waybill ready /path/to/your/repo/.waybill --repo /path/to/your/repo
```

For scripts:

```bash
./cli/waybill validate /path/to/your/repo/.waybill --json
./cli/waybill preflight /path/to/your/repo/.waybill --repo /path/to/your/repo --json
./cli/waybill ready /path/to/your/repo/.waybill --repo /path/to/your/repo --json
```

Every JSON-capable command writes exactly one JSON object. Its top-level
boolean `success` is `true` exactly when the command exits zero; JSON failures
do not include ordinary text or a traceback.

## 5. Share Safely

Review `.waybill/` before sharing it. It can contain prompts, paths, diffs,
logs, test output, tokens, cookies, API keys, or customer data.

First run the read-only shareability check. It requires no output path and
writes nothing:

```bash
./cli/waybill share /path/to/your/repo/.waybill --check
./cli/waybill share /path/to/your/repo/.waybill --check --json
```

The exit code is zero only when the bundle is shareable. JSON findings expose
only `kind`, `path`, `count`, and `blocking`; matched secret values are never
printed.

Create a redacted archive:

```bash
./cli/waybill share /path/to/your/repo/.waybill --output /tmp/waybill.zip
```

Create a Markdown review report:

```bash
./cli/waybill render /path/to/your/repo/.waybill --output /tmp/waybill-report.md
```

## Agent Smoke Tests

When the local CLIs are installed and authenticated, run repeatable read-only
import checks from the Waybill repository:

```bash
scripts/smoke-agents.sh --tool codex
scripts/smoke-agents.sh --tool opencode
scripts/smoke-agents.sh --tool cursor
scripts/smoke-agents.sh --tool gemini
scripts/smoke-agents.sh --tool claude
```

Print the exact commands without calling any model:

```bash
scripts/smoke-agents.sh --dry-run
```

For strict semantic scenarios with measured workspace write detection, use the
conformance runner documented in `CONFORMANCE.md`.

## Notes

- Waybill is local-first; it does not upload handoff data.
- `.waybill/` is ignored by default.
- Import is intentionally non-destructive: it reads and summarizes first.
- Some agent CLIs write local session or log files outside the repository.
- Gemini CLI plan mode may not expose shell tools. It should still read the
  bundle and report obvious repository mismatches from available context.
