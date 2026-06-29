# Waybill Bundle Specification

Schema status: `draft`

Waybill Bundle is a local, agent-neutral handoff directory for an unfinished
task. It is designed to be readable by humans and usable by coding agents.

## Directory

The default bundle path is:

```text
.waybill/
```

The bundle should live at the repository root unless the user gives another
path.

## Files

Required:

- `WAYBILL.md`: Human and agent readable handoff summary.
- `metadata.json`: Machine readable bundle metadata.

Recommended:

- `diff.patch`: Current uncommitted diff, usually from `git diff`.
- `commands.log`: Important commands that were run or considered relevant.
- `test-summary.md`: Test and verification status.

Adapters may include additional files, but importers must not require them for
basic handoff.

## Command Names

The primary command is:

```text
/handoff
```

The alias is:

```text
/waybill
```

These pairs are equivalent:

```text
/handoff export
/waybill export
```

```text
/handoff import .waybill
/waybill import .waybill
```

## Export Behavior

An adapter exporting a bundle should:

1. Identify the original task goal from the current conversation.
2. Inspect the current repository state with read-only commands such as:
   - `git status --short`
   - `git branch --show-current`
   - `git rev-parse HEAD`
   - `git diff`
3. Create `.waybill/`.
4. Write `WAYBILL.md` using the exact section headings from the standard
   template.
5. Write `metadata.json`.
6. Write recommended artifacts when information is available.
7. Mark facts, assumptions, verified results, and unverified claims clearly.
8. In `commands.log`, separate read-only inspection commands from bundle-writing
   actions. Do not claim every command was read-only if `.waybill/` was created
   or files were written.
9. Remind the user to review the bundle for sensitive information.

Export instructions may run read-only git commands. They should not run tests
unless the user explicitly asks.

## Import Behavior

An adapter importing a bundle should:

1. Read `WAYBILL.md`.
2. Read `metadata.json`.
3. Inspect the current repository state before acting.
4. Compare the handoff summary with the real files and git state.
5. Summarize the task, progress, risks, and next recommended step.
6. Ask or proceed according to the user's current instruction.

Import instructions must not blindly trust the bundle. They must not
automatically apply `diff.patch` or run dangerous commands.

## Security

`.waybill/` may contain sensitive information, including prompts, file paths,
diffs, logs, test output, tokens, cookies, API keys, or customer data.

Default policy:

- Keep `.waybill/` in `.gitignore`.
- Do not upload bundle contents.
- Do not commit real handoff bundles by default.
- Use synthetic data in examples.
- Ask users to review contents before sharing.

## Agent Neutrality

Bundle content should not require a specific source or target agent. Prefer
phrases such as "the next agent should" instead of "Claude should" or "Codex
should" inside `WAYBILL.md`.
