# Waybill Delegation Semantics

Schema status: `draft`

Delegation extends a normal Waybill Bundle with parent/child task semantics. It
does not turn Waybill into an agent runner, scheduler, queue, or process
manager. A delegation bundle is still a local directory that importers read,
verify, and summarize before taking action.

## Metadata

Delegation-aware bundles use optional `metadata.json` handoff metadata:

```json
{
  "handoff": {
    "kind": "delegation_request"
  }
}
```

Allowed `handoff.kind` values:

- `handoff`: Ordinary agent-to-agent task handoff. This is the default when
  `handoff.kind` is absent.
- `delegation_request`: A parent agent is asking a child agent to perform a
  bounded subtask and return a result.
- `delegation_result`: A child agent is returning completed work, findings, or
  a proposed patch to a parent agent for review.

Importers that do not understand delegation can still read the standard
`WAYBILL.md` sections. Delegation-aware importers should use `handoff.kind` to
select the correct review posture.

## Delegation Requests

A delegation request must include the standard `WAYBILL.md` sections and these
additional sections:

- `Delegation Request`: Why this subtask is being delegated.
- `Child Agent Task`: The bounded task the child agent should perform.
- `Acceptance Criteria`: Conditions the child agent should satisfy before
  returning.
- `Return Instructions`: What the child agent should export or report back.

The request must keep the child task bounded. It should not ask the child agent
to take ownership of unrelated work, rewrite broad architecture, or perform
dangerous commands.

## Delegation Results

A delegation result must include the standard `WAYBILL.md` sections and these
additional sections:

- `Delegation Result`: Whether the child task was completed, partially
  completed, or blocked.
- `Work Completed`: Concrete files, behavior, and verification completed by the
  child agent.
- `Parent Review Notes`: Facts, assumptions, and risks the parent agent should
  inspect before accepting the result.
- `Parent Next Step`: One concrete next action for the parent agent.

The result is advisory until the parent agent reviews it. Importers must not
automatically apply `diff.patch`, merge changes, or accept a child result just
because the bundle validates.

Delegation importers must not automatically apply `diff.patch`.

## Safety

Delegation bundles may contain broader task context than a one-off handoff.
Keep them local by default, redact before sharing, and avoid real customer data,
tokens, local paths, or private logs in public examples.
