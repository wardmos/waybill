---
description: Export or import a Waybill Bundle for coding-agent handoff
---

Use the `handoff` skill to run the Waybill handoff workflow.

Arguments:

```text
$ARGUMENTS
```

Dispatch:

- `export`: create `.waybill/` for the current unfinished task.
- `import <bundle-path>`: read a Waybill Bundle, verify current repo state, and
  continue only after grounding the next step.
- If no import path is provided, use `.waybill/`.
- If the arguments are unclear, ask whether to export or import.
