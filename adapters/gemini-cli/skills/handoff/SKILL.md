---
name: handoff
description: Export or import local Waybill Bundles for unfinished coding-agent tasks. Use when the user asks for handoff, waybill, their export or import forms, or wants to continue from a Waybill bundle.
---

# Waybill Handoff for Gemini CLI

This is a thin Gemini CLI wrapper around the shared Waybill handoff workflow.
For exports, use `gemini-cli` as `source_agent`; never claim another product
created the bundle.

Read the [shared dispatch](references/dispatch.md) completely and follow it for
the user's request.

`handoff` is the primary workflow and `waybill` is an alias.
