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

This guide uses the agent-native Skill workflow. It does not require the
Waybill CLI, a Python package, or a separate Waybill process.

The shared dispatch and operation workflow live only in `skills/handoff/`.
Agent-specific files under `adapters/` are thin source wrappers containing only
platform metadata and routing details. The support CLI installs them directly,
or `scripts/build-adapters.py` creates self-contained distributions.

## 1. Enable The Agent-Native Skill

### Codex

Enable the repository's Codex plugin through Codex plugin management:

```bash
codex plugin marketplace add .
codex plugin add waybill@waybill-local
```

You can also select `Waybill` from the `Waybill Local` marketplace in the Codex
plugin UI. Start a new thread after enabling it. This installs the Skill plugin,
not the Waybill CLI.

### Claude Code

Build the standalone adapters, then ask Claude Code to copy these directories
into the target repository without replacing existing paths unless you approve
it:

```bash
python3 scripts/build-adapters.py
```

```text
dist/adapters/claude-code/skills/handoff/ -> .claude/skills/handoff/
dist/adapters/claude-code/skills/waybill/ -> .claude/skills/waybill/
```

Then start a new Claude Code session in the target repository. The copied Skill
contains everything needed for basic export and import, without the Waybill
CLI.

See `INSTALL.md` for OpenCode, Cursor, and Gemini CLI copy paths.

### Optional Managed Setup

Use the support CLI only when you want conflict preflight, multi-adapter
installation, a managed-file manifest, and installation diagnostics:

```bash
./cli/waybill init --target /path/to/your/repo --dry-run
./cli/waybill init --target /path/to/your/repo
./cli/waybill doctor --target /path/to/your/repo
```

A successful install atomically records managed files and digests in the
deterministic, timestamp-free `.waybill-adapters.json` manifest. `doctor`
reports each managed file as `current`, `missing`, `stale`, or `modified`. For
an older installation without a manifest, a file that differs from the current
template is `modified`; it cannot be reliably distinguished as an untouched
stale install or a local edit. Codex remains outside this optional lifecycle.

## 2. Export A Handoff

In the agent where the task is currently stuck or unfinished, ask for:

```text
/handoff
```

The alias has the same behavior:

```text
/waybill
```

The direction is optional: `/handoff` defaults to `export`. The explicit
`/handoff export` and `/waybill export` forms remain supported.

Expected result:

- `.waybill/` is created in the target repository.
- `WAYBILL.md` summarizes the goal, status, changed files, tests, risks, and
  next step.
- `metadata.json` records branch, HEAD, dirty state, and artifact paths. Exact
  repository digests are included only when a trusted helper calculated them.
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

When Python 3 is already available, the Skill's single bundled checker can
verify a request/result pair without changing either bundle or repository:

```bash
python3 /path/to/handoff/scripts/check_bundle.py /path/to/result \
  --repo /path/to/repo --request /path/to/request --json
```

Without Python, the importing agent compares the correlation fields directly.

## 4. Optional Enhanced Validation

Basic export and import include direct checks performed by the agent. If
Python 3 is already available, run the Skill's bundled read-only checker:

```bash
python3 /path/to/handoff/scripts/check_bundle.py \
  /path/to/your/repo/.waybill --repo /path/to/your/repo --json
```

The checker is self-contained and does not import or invoke the Waybill CLI.
Use the optional support CLI when you want deeper automation outside an agent:

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

Manual review needs no CLI. If the optional support CLI is available, its
read-only shareability check requires no output path and writes nothing:

```bash
./cli/waybill share /path/to/your/repo/.waybill --check
./cli/waybill share /path/to/your/repo/.waybill --check --json
```

The exit code is zero only when the bundle is shareable. JSON findings expose
only `kind`, `path`, `count`, and `blocking`; matched secret values are never
printed.

The optional CLI can also create a redacted archive:

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
