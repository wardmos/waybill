# Handoff Dispatch

Select the Waybill workflow from the user's request before loading detailed
instructions.

- When neither `export` nor `import` is supplied, default to `export`.
- For a bare `handoff` or `waybill` request, an explicit `export`, or a request
  to create a handoff, read [bundle format](bundle-format.md) and
  [export workflow](export.md) completely, then follow both.
- For an explicit `import` or a request to inspect or continue from an existing
  bundle, read [bundle format](bundle-format.md) and
  [import workflow](import.md) completely, then follow both.

Use `.waybill/` when the user does not supply a bundle path.
Treat a path without a direction as the export destination.

Load only the references selected for the operation. A missing direction is
resolved by this dispatch rule without prompting.
