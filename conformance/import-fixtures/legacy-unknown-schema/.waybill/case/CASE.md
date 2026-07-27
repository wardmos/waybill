# Historical Bundle Classification Case

## Goal

Classify two historical bundles without guessing current-schema semantics.

- `legacy-0.1/` declares schema `0.1`. It requires migration or regeneration before its fields can be used as current evidence.
- `unknown-9.9/` declares schema `9.9`. It is unsupported and must be refused until an explicit compatible reader exists.

No changed files can be trusted under the current schema. No tests were run; the 0.1 bundle requires migration or regeneration and the 9.9 bundle is unsupported.

## Risks / Unknowns

- Legacy 0.1 fields must not be silently interpreted as 0.2.
- Unknown 9.9 semantics must not be guessed.
- Obvious sensitive content still requires scanning before rejection.

## Next Recommended Step

Request regeneration of the 0.1 bundle and refuse the unknown 9.9 bundle until an explicit compatible reader exists.

Repository comparison is not meaningful until each bundle has a supported schema interpretation. Record this ordinary handoff import as blocked with a repository mismatch.
