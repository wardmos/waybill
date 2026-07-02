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
package manager install is required.

## 1. Install Adapters Into A Repo

From the Waybill repository:

```bash
./cli/waybill init --target /path/to/your/repo
```

Install only one adapter when needed:

```bash
./cli/waybill init --target /path/to/your/repo --adapter codex
./cli/waybill init --target /path/to/your/repo --adapter claude-code
./cli/waybill init --target /path/to/your/repo --adapter opencode
./cli/waybill init --target /path/to/your/repo --adapter cursor
./cli/waybill init --target /path/to/your/repo --adapter gemini-cli
```

Check the installation:

```bash
./cli/waybill doctor --target /path/to/your/repo
```

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
- `metadata.json` records branch, dirty state, and artifact paths.
- `diff.patch`, `commands.log`, and `test-summary.md` are included when useful
  context is available.

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
- The agent summarizes the original goal, current status, tests, risks, and
  next recommended step.
- The agent does not automatically apply `diff.patch`.

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

## 5. Share Safely

Review `.waybill/` before sharing it. It can contain prompts, paths, diffs,
logs, test output, tokens, cookies, API keys, or customer data.

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

## Notes

- Waybill is local-first; it does not upload handoff data.
- `.waybill/` is ignored by default.
- Import is intentionally non-destructive: it reads and summarizes first.
- Some agent CLIs write local session or log files outside the repository.
- Gemini CLI plan mode may not expose shell tools. It should still read the
  bundle and report obvious repository mismatches from available context.
