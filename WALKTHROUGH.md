# Waybill Walkthrough

This walkthrough shows how the synthetic Waybill examples map to the
user-facing handoff flow. It uses local files only and does not require running
an agent model. The real handoff flow runs through the agent-native Skill and
does not require the Waybill CLI; CLI commands below are optional enhanced
inspection examples.

## Scenario

A parent agent is working on a queue retry-limit fix. The parent has enough
context to define a bounded subtask, but wants another agent to inspect the
retry counter path and return a result for review.

The example flow is:

```text
Claude Code parent
  -> delegation request bundle
  -> Codex child
  -> delegation result bundle
  -> parent review
```

The public fixtures are synthetic:

```text
examples/claude-parent-codex-child-request/
examples/claude-parent-codex-child-result/
```

## 1. Parent Creates A Delegation Request

In a real agent session, the user asks the parent agent to delegate a bounded
subtask:

```text
/handoff export
```

For delegation, the exported `metadata.json` includes:

```json
{
  "handoff": {
    "kind": "delegation_request",
    "request_id": "queue-retry-limit-inspection-001",
    "parent_agent": "claude-code",
    "child_agent": "codex"
  }
}
```

The request bundle still has the standard Waybill files:

```text
WAYBILL.md
metadata.json
diff.patch
commands.log
test-summary.md
```

It also adds request-specific sections in `WAYBILL.md`:

- `Delegation Request`
- `Child Agent Task`
- `Acceptance Criteria`
- `Return Instructions`

If the optional support CLI is already available, inspect the synthetic
request:

```bash
./cli/waybill validate examples/claude-parent-codex-child-request
./cli/waybill inspect examples/claude-parent-codex-child-request
./cli/waybill render examples/claude-parent-codex-child-request --output /tmp/waybill-delegation-request.md --force
```

Expected result:

- Validation passes.
- Metadata reports `handoff.kind` as `delegation_request`.
- The request tells the child agent what to inspect, what counts as done, and
  how to return the result.

## 2. Child Imports The Request

In the child agent, the user imports the request:

```text
/handoff import examples/claude-parent-codex-child-request
```

The child agent should:

- Read `WAYBILL.md` and `metadata.json`.
- Verify the current repository state before trusting the bundle.
- Notice `handoff.kind: delegation_request`.
- Treat the bundle as a bounded child-agent task.
- Avoid automatically applying `diff.patch`.
- Summarize the child task, acceptance criteria, risks, and next action before
  making changes.

The child agent should not treat the request as ownership of the whole parent
task. It should perform or propose the bounded work and return a result.

## 3. Child Returns A Delegation Result

After the child completes the bounded task, it exports a result bundle:

```text
/handoff export
```

For a result, `metadata.json` includes:

```json
{
  "handoff": {
    "kind": "delegation_result",
    "result_for": "queue-retry-limit-inspection-001",
    "result_status": "completed",
    "parent_agent": "claude-code",
    "child_agent": "codex"
  }
}
```

The result bundle still has the standard Waybill sections and adds:

- `Delegation Result`
- `Work Completed`
- `Parent Review Notes`
- `Parent Next Step`

If the optional support CLI is already available, inspect the synthetic result:

```bash
./cli/waybill validate examples/claude-parent-codex-child-result
./cli/waybill inspect examples/claude-parent-codex-child-result
./cli/waybill render examples/claude-parent-codex-child-result --output /tmp/waybill-delegation-result.md --force
```

Expected result:

- Validation passes.
- Metadata reports `handoff.kind` as `delegation_result`.
- The result tells the parent what the child found, what changed, what was
  verified, and what still needs review.

## 4. Parent Reviews The Result

The parent imports the child result:

```text
/handoff import examples/claude-parent-codex-child-result
```

The parent compares `request_id`, `result_for`, roles, and source agents
directly. If the optional support CLI is already available, it can repeat that
pair check without changing either bundle:

```bash
./cli/waybill verify-pair examples/claude-parent-codex-child-request \
  examples/claude-parent-codex-child-result
```

The parent agent should:

- Verify the current repository state.
- Verify the correlation ID, result status, roles, and sources.
- Notice `handoff.kind: delegation_result`.
- Treat the bundle as advisory child-agent output.
- Inspect `diff.patch` before applying or recreating any change.
- Review risks and test state before accepting the result.
- Decide the next parent action.

Import remains non-destructive. A valid delegation result does not mean the
patch should be applied automatically.

## 5. Why This Is Not Orchestration

Delegation gives Waybill enough structure to pass a bounded task between agents.
It does not schedule agents, launch child processes, manage queues, merge
patches, or supervise long-running work.

Waybill stays a local, reviewable envelope:

- The parent decides what to delegate.
- The child returns facts, work, and risks.
- The parent reviews before accepting the result.
- The user remains in control of sharing and applying changes.

## Quick Validation

Run the repository checks:

```bash
python3 scripts/validate-waybill.py
```

Run read-only smoke commands without calling model CLIs:

```bash
scripts/smoke-agents.sh --dry-run
```
