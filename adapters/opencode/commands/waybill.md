---
description: Alias for the Waybill handoff command
---

Use the `handoff` skill to run the Waybill handoff workflow.

Arguments:

```text
$ARGUMENTS
```

`/waybill` is an alias for `/handoff`:

- `export`: create `.waybill/` for the current unfinished task.
- `import <bundle-path>`: read a Waybill Bundle, verify current repo state, and
  continue only after grounding the next step.
- If no import path is provided, use `.waybill/`.
