---
description: Export or import local Waybill Bundles for unfinished coding-agent tasks. Use when the user asks for /handoff, /handoff export, /handoff import, or wants to continue from a Waybill bundle.
argument-hint: "[export | import] [bundle-path]"
---

# Waybill Handoff for Claude Code

This is a thin Claude Code wrapper around the shared Waybill handoff workflow.
For exports, use `claude-code` as `source_agent`; never claim another product
created the bundle.

Arguments are available as `$ARGUMENTS`.

Read the [shared dispatch](references/dispatch.md) completely and follow it,
using `$ARGUMENTS` as the request arguments.

`/handoff` is the primary command. `/waybill` is provided by the sibling alias
skill.
