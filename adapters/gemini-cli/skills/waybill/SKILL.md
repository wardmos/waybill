---
name: waybill
description: Alias for the Waybill handoff workflow. Use when the user asks for waybill export, waybill import, export a Waybill bundle, or import a Waybill bundle.
---

# Waybill Alias

This skill is an alias for the `handoff` skill.

Use this skill when the user asks for:

```text
waybill export
waybill import .waybill
export a Waybill bundle
import a Waybill bundle
```

Run the same behavior as the `handoff` skill:

- `export`: create a local `.waybill/` bundle for the current unfinished task.
- `import <bundle-path>`: read an existing bundle, verify current repo state,
  summarize the handoff, and continue only after grounding the next step.

## Required Bundle Files

- `WAYBILL.md`
- `metadata.json`

## Recommended Bundle Files

- `diff.patch`
- `commands.log`
- `test-summary.md`

## Export Rules

- Generate agent-neutral content.
- Use `.waybill/` as the default output directory.
- Do not run tests unless the user explicitly asks.
- Do not upload or share bundle contents.
- Write `metadata.json` with `source_agent` set to `gemini-cli`.
- Write `WAYBILL.md` using the exact section headings from
  `spec/waybill-template.md`. Do not rename, omit, or substitute headings.
- In `commands.log`, separate read-only inspection commands from bundle-writing
  actions. Do not claim every command was read-only if `.waybill/` was created
  or files were written.

## Import Rules

- Read the bundle before acting.
- Verify the current repository state before trusting the bundle.
- Do not automatically apply `diff.patch`.
- Do not run dangerous commands.
- Do not assume the source agent is available.

## Import Summary

When importing, summarize:

- Original goal
- Current status
- Changed files
- Test state
- Failed attempts
- Risks and unknowns
- Next recommended step

## Safety

`.waybill/` may contain prompts, paths, diffs, logs, test output, tokens,
cookies, API keys, or customer data. Keep it local unless the user explicitly
chooses to share it.
