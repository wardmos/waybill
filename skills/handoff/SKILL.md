---
name: handoff
description: Export or import local Waybill Bundles for unfinished coding-agent tasks. Use for /handoff, /waybill, or requests to create, inspect, or continue from a Waybill handoff or delegation bundle.
---

# Waybill Handoff for Codex

Waybill is an agent-neutral, local-first handoff format for unfinished coding
tasks. This repository-root Skill is the Codex entrypoint. For exports, use
`codex` as `source_agent`; never claim another product created the bundle.

Read the [shared dispatch](references/dispatch.md) completely and follow it for
the user's request.

`/handoff` is the primary workflow and `/waybill` is an alias. Supported forms
include `/handoff export`, `/waybill export`, `/handoff import`, and
`/waybill import`.
