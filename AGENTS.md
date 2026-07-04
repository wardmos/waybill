# AGENTS.md

Waybill creates portable, local-first handoff bundles for moving unfinished
agent work between coding agents.

- Keep specs, examples, adapters, and generated text portable across agent CLIs.
- Keep `.agents/`, `.claude/`, `.cursor/`, `.gemini/`, tracked `.opencode/`
  command/skill files, and `adapters/` in git; they are project deliverables.
- Do not commit local artifacts such as handoff bundles, package installs,
  caches, bytecode, archives, or generated reports.
- Keep changes small, focused, and consistent with existing module boundaries.
- Do not add dependencies unless clearly justified; prefer the Python standard
  library.

## Privacy

- Do not commit secrets, tokens, API keys, cookies, private user data, personal
  emails, local machine paths, real handoff bundles, archives, logs, screenshots,
  or private planning notes.
- Keep examples and tests synthetic.
- Do not weaken privacy, redaction, bundle validation, packing, or unpacking
  safeguards without focused tests.
- Do not add release tags or release wording until an actual release is being
  prepared.

## Checks

- Run `python3 scripts/validate-waybill.py` after code, adapter, spec, example,
  or docs changes.
- For Python changes, also run
  `python3 -m py_compile cli/waybill waybill_core/*.py scripts/validate-waybill.py`.
- Add or update validation coverage for behavior changes, bug fixes, and
  privacy-sensitive paths. If a check cannot run locally, document why.
- Use `scripts/smoke-agents.sh --dry-run` for smoke command generation. Only run
  real agent smoke tests when explicitly asked.

## Commit Messages

- Use Conventional Commit style: `type(scope): subject`, or `type: subject`
  when there is no clear scope.
- Describe only the code change in the commit message. Do not include local
  paths, local test details, or private planning notes.

## Git History

- Do not rewrite commits that have already been pushed to a remote.
- Do not amend pushed commits, rebase pushed commits, or force push over pushed
  history.
- If a pushed branch needs more changes, add a new commit instead.
- Do not discard or revert changes you did not make unless explicitly asked.
