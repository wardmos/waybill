---
name: handoff
description: Export or import local Waybill Bundles for unfinished coding-agent tasks. Use when the user asks for /handoff, /waybill, their export or import forms, or wants to continue from a Waybill bundle.
compatibility: opencode
---

# Waybill Handoff for OpenCode

This is a thin OpenCode wrapper around the shared Waybill handoff workflow. For
exports, use `opencode` as `source_agent`; never claim another product created
the bundle.

Read the [shared dispatch](references/dispatch.md) completely and follow it for
the user's request.

`/handoff` is the primary command and `/waybill` is an alias.
