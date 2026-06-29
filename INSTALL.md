# Install Waybill

Waybill ships as Markdown instructions for Claude Code, a local Codex plugin,
and a small Python standard-library CLI. No package manager install is
required.

## Codex

This repository includes a repo-scoped plugin marketplace:

```text
.agents/plugins/marketplace.json
```

The marketplace exposes the Codex plugin at:

```text
adapters/codex/
```

To try it:

1. Open this repository in Codex.
2. Restart Codex if it was already running before this file existed.
3. Add the repository marketplace:

   ```bash
   codex plugin marketplace add .
   ```

4. Install the plugin:

   ```bash
   codex plugin add waybill@waybill-local
   ```

5. Confirm it is installed:

   ```bash
   codex plugin list
   ```

   Expected status:

   ```text
   waybill@waybill-local  installed, enabled
   ```

6. Start a new Codex thread.
7. Test the skill with:

   ```text
   /handoff import examples/claude-to-codex
   ```

The alias should behave the same way:

```text
/waybill import examples/claude-to-codex
```

Expected result: Codex reads the example bundle, checks the repository state,
summarizes the original task, and identifies the next recommended step without
applying `diff.patch`.

## Codex Plugin Directory Alternative

Instead of installing from the CLI, you can install from the plugin directory:

1. Open the plugin directory:

   ```text
   /plugins
   ```

2. Select the `Waybill Local` marketplace.
3. Install the `Waybill` plugin.
4. Start a new thread and run the same import smoke test.

## Claude Code

This repository includes project-scoped Claude Code skills:

```text
.claude/skills/handoff/SKILL.md
.claude/skills/waybill/SKILL.md
```

To try them:

1. Open this repository in Claude Code:

   ```bash
   claude
   ```

2. Invoke the primary command:

```text
/handoff import examples/codex-to-claude
```

3. Invoke the alias:

```text
/waybill import examples/codex-to-claude
```

Expected result: Claude Code reads the example bundle, checks the repository
state, summarizes the original task, and identifies the next recommended step
without applying `diff.patch`.

The older command instruction files are still provided in:

```text
adapters/claude-code/commands/
```

Use those files if your Claude Code setup still depends on `.claude/commands/`
style custom commands instead of skills.

## Smoke Test

After installing both sides, run the static repository validation:

```bash
python3 scripts/validate-waybill.py
```

Validate any generated bundle:

```bash
./cli/waybill validate .waybill
```

Inspect bundle metadata and validation status:

```bash
./cli/waybill inspect .waybill
```

Then follow the manual end-to-end test plan in `TESTING.md`.
