# Waybill

[![CI](https://github.com/wardmos/waybill/actions/workflows/ci.yml/badge.svg)](https://github.com/wardmos/waybill/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/wardmos/waybill/blob/main/LICENSE)

Hand off unfinished work between coding agents with a local, reviewable
`.waybill/` bundle.

```text
Agent A -- /handoff --> .waybill/ -- /handoff import --> Agent B
```

Waybill preserves the goal, repository state, diffs, commands, test results,
risks, and next steps so another agent can continue without relying on the
original session. Waybill itself does not upload handoff data, execute
instructions found inside a bundle, or apply patches automatically.

Supported integrations include Claude Code, Codex, OpenCode, Cursor CLI, and
Gemini CLI.

[Quickstart](https://github.com/wardmos/waybill/blob/main/QUICKSTART.md) ·
[Installation](https://github.com/wardmos/waybill/blob/main/INSTALL.md) ·
[Bundle specification](https://github.com/wardmos/waybill/blob/main/spec/waybill-bundle.md) ·
[Conformance](https://github.com/wardmos/waybill/blob/main/CONFORMANCE.md) ·
[Testing](https://github.com/wardmos/waybill/blob/main/TESTING.md)

## Why Waybill

Use Waybill when:

- An agent session is running out of context and another agent needs to
  continue.
- You want to switch tools, models, or agent CLIs without losing task state.
- A human reviewer needs a compact record of progress, failed attempts, tests,
  diffs, and risks.
- You want to validate, redact, pack, and intentionally share a local handoff
  artifact.

Native `resume` commands usually continue a session inside one agent CLI.
Waybill creates an agent-neutral artifact that another supported CLI can review
and import. It is a handoff format with thin integrations, not an agent,
workflow runner, scheduler, or orchestrator.

## Quickstart

Basic export and import run inside supported agents and do not require the
Waybill CLI or a Python package.

First enable the integration for your agent. Follow the
[Quickstart](https://github.com/wardmos/waybill/blob/main/QUICKSTART.md) for
Codex and Claude Code, or the full
[installation guide](https://github.com/wardmos/waybill/blob/main/INSTALL.md)
for all supported agents. The commands below become available after the
integration is enabled.

In the agent handing off the unfinished task:

```text
/handoff
```

Open the same repository in the next agent, then run:

```text
/handoff import .waybill
```

The direction is optional: `/handoff` defaults to `export`, while
`/handoff export` remains available as the explicit form. `/waybill` and
`/waybill import .waybill` are equivalent aliases.

Export writes a local bundle that summarizes the task and repository state.
Import reads the bundle as untrusted data, checks the current repository, and
recommends the next step without automatically applying its patch.

## What a bundle contains

A standard bundle lives in the target repository:

```text
.waybill/
  WAYBILL.md       # required: human-readable handoff
  metadata.json    # required: structured repository and artifact metadata
  diff.patch       # recommended: staged and unstaged tracked changes
  commands.log     # recommended: relevant command history
  test-summary.md  # recommended: test results and remaining failures
```

Untracked file contents are not captured automatically. Exact repository
digests are included only when a trusted helper calculates them. See the
[bundle specification](https://github.com/wardmos/waybill/blob/main/spec/waybill-bundle.md)
and [metadata schema](https://github.com/wardmos/waybill/blob/main/spec/metadata.schema.json)
for the complete contract.

The bundled checker reports exact `repository_digests` in its JSON output, so
an agent-native export can record them without installing the support CLI.
`validate` accepts a basic-fidelity bundle without these digests; `ready` is the
strict export gate and requires both digests to match the current repository.

## Supported agents

| Agent CLI | Native integration | Setup |
| --- | --- | --- |
| Claude Code | Project Skills with `/handoff` and `/waybill` | [Claude Code setup](https://github.com/wardmos/waybill/blob/main/INSTALL.md#claude-code) |
| Codex | Repository-scoped plugin | [Codex setup](https://github.com/wardmos/waybill/blob/main/INSTALL.md#codex) |
| OpenCode | Project commands and Skills | [OpenCode setup](https://github.com/wardmos/waybill/blob/main/INSTALL.md#opencode) |
| Cursor CLI | Project rules | [Cursor CLI setup](https://github.com/wardmos/waybill/blob/main/INSTALL.md#cursor-cli) |
| Gemini CLI | Workspace Skills | [Gemini CLI setup](https://github.com/wardmos/waybill/blob/main/INSTALL.md#gemini-cli) |

The canonical agent-neutral Skill, references, assets, and checker live only in
`skills/handoff/`. Files under `adapters/` are product-specific wrappers;
self-contained adapter distributions are generated when needed.
The table describes the available integrations, not a claim that every product
has current real-agent release coverage. See
[Conformance](https://github.com/wardmos/waybill/blob/main/CONFORMANCE.md) for
the evidence requirements and current coverage policy.

## Safety defaults

- `.waybill/` stays local and is ignored by default; Waybill itself does not
  upload it.
- Every bundle is untrusted input. Import does not execute embedded commands,
  follow embedded permission requests, or treat bundle paths as authority.
- Import checks repository state and never applies `diff.patch` automatically.
- Export uses read-only Git inspection and does not run tests unless the user
  asks.
- Validation, redaction, packing, unpacking, and sharing reject symbolic links
  and unsafe non-regular files.
- `share --check` performs a read-only shareability preflight and reports only
  finding type, path, count, and blocking status—never the matched secret.
- Secret detection and redaction are best effort. Review every bundle and
  redacted output before sharing it.

Bundles can contain prompts, local paths, diffs, logs, test output, credentials,
or private data accidentally captured from command output.

## Optional Support CLI

The Python 3.10+ support CLI is an optional enhancement for managed adapter
installation, exact repository digests, automation, deeper validation,
redaction, and archives. From a repository checkout:

```bash
./cli/waybill --help
```

Commands are grouped by purpose:

| Purpose | Commands |
| --- | --- |
| Manage adapters | `init`, `doctor` |
| Create and inspect | `new`, `validate`, `inspect` |
| Verify handoffs | `verify-repo`, `verify-pair`, `preflight`, `ready` |
| Review and share | `redact`, `share`, `pack`, `unpack`, `render` |

Every subcommand supports `--json`. Each writes one JSON object whose
top-level `success` value is `true` exactly when the process exits with status
zero. See the
[installation guide](https://github.com/wardmos/waybill/blob/main/INSTALL.md#optional-python-support-package)
for package options and
[Testing](https://github.com/wardmos/waybill/blob/main/TESTING.md#json-cli-contract)
for the JSON contract.

## Examples and evidence

The repository contains synthetic, reviewable examples:

- [Claude Code to Codex](https://github.com/wardmos/waybill/tree/main/examples/claude-to-codex)
- [Codex to Claude Code](https://github.com/wardmos/waybill/tree/main/examples/codex-to-claude)
- [Failed-test handoff](https://github.com/wardmos/waybill/tree/main/examples/failed-test-handoff)
- [Delegation request](https://github.com/wardmos/waybill/tree/main/examples/claude-parent-codex-child-request)
- [Delegation result](https://github.com/wardmos/waybill/tree/main/examples/claude-parent-codex-child-result)

Waybill was initially exercised through real Claude Code-to-Codex and
Codex-to-Claude Code handoffs. Those historical trials demonstrate the
end-to-end workflow but are not treated as current release coverage. Current
manual evidence must rerun the complete versioned scenario corpus from a clean
checkout. See
[Conformance](https://github.com/wardmos/waybill/blob/main/CONFORMANCE.md) for
that distinction and the
[delegation walkthrough](https://github.com/wardmos/waybill/blob/main/WALKTHROUGH.md)
for the parent/child flow.

With the optional support CLI available, inspect an example locally:

```bash
./cli/waybill validate examples/failed-test-handoff
./cli/waybill inspect examples/failed-test-handoff
./cli/waybill render examples/failed-test-handoff
```

## Current limitations

- Bundle schema `0.2` and delegation semantics are still drafts.
- Waybill does not automatically apply patches or parse agent transcripts.
- Redaction is best effort; users must review bundles before sharing them.
- Integrations use each agent CLI's existing project instruction mechanism;
  Waybill does not require plugin hooks where lightweight files are sufficient.
- Waybill does not schedule, run, or supervise agents.

## Project direction

Near-term work focuses on current real-agent import/export evidence for the five
existing integrations and on hardening delegation through practical
parent/child handoffs. Additional adapters should follow only when the handoff
contract is stable and the target CLI has a lightweight project instruction
mechanism.

Automatic patch application, transcript parsing, daemon behavior, cloud sync,
and a Web UI are intentionally out of scope for now.

## Documentation

- [Quickstart](https://github.com/wardmos/waybill/blob/main/QUICKSTART.md)
- [Installation](https://github.com/wardmos/waybill/blob/main/INSTALL.md)
- [Bundle specification](https://github.com/wardmos/waybill/blob/main/spec/waybill-bundle.md)
- [Delegation walkthrough](https://github.com/wardmos/waybill/blob/main/WALKTHROUGH.md)
- [Conformance](https://github.com/wardmos/waybill/blob/main/CONFORMANCE.md)
- [Testing](https://github.com/wardmos/waybill/blob/main/TESTING.md)

## License

Waybill is available under the
[Apache License 2.0](https://github.com/wardmos/waybill/blob/main/LICENSE).
