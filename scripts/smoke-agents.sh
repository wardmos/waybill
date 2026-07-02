#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="examples/claude-to-codex"
DRY_RUN=0
TIMEOUT_SECONDS="${WAYBILL_SMOKE_TIMEOUT:-180}"
GEMINI_MODEL="${WAYBILL_GEMINI_MODEL:-gemini-3.1-flash-lite}"
TOOLS=()

usage() {
  cat <<'EOF'
Usage: scripts/smoke-agents.sh [options]

Run repeatable read-only import smoke tests for Waybill agent adapters.

Options:
  --tool <name>       Tool to test: claude, codex, cursor, opencode, gemini, all.
                      May be passed more than once. Defaults to all.
  --bundle <path>     Bundle path relative to the repo root.
                      Defaults to examples/claude-to-codex.
  --dry-run           Print commands without executing them.
  -h, --help          Show this help.

Environment:
  WAYBILL_SMOKE_TIMEOUT       Per-tool timeout in seconds. Defaults to 180.
  WAYBILL_GEMINI_MODEL        Gemini model. Defaults to gemini-3.1-flash-lite.

The script fails if the repository is dirty before or after a tool runs.
It writes command logs to a temporary directory under /tmp.
EOF
}

add_tool() {
  local tool="$1"
  if [[ "$tool" == "all" ]]; then
    TOOLS=(claude codex cursor opencode gemini)
    return
  fi
  case "$tool" in
    claude|codex|cursor|opencode|gemini) TOOLS+=("$tool") ;;
    *) echo "Unknown tool: $tool" >&2; exit 2 ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tool)
      [[ $# -ge 2 ]] || { echo "--tool requires a value" >&2; exit 2; }
      add_tool "$2"
      shift 2
      ;;
    --bundle)
      [[ $# -ge 2 ]] || { echo "--bundle requires a value" >&2; exit 2; }
      BUNDLE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${#TOOLS[@]} -eq 0 ]]; then
  add_tool all
fi

if [[ ! -d "$ROOT/$BUNDLE" ]]; then
  echo "Bundle not found: $BUNDLE" >&2
  exit 1
fi

require_clean_repo() {
  local phase="$1"
  local status
  status="$(git -C "$ROOT" status --short)"
  if [[ -n "$status" ]]; then
    echo "Repository is not clean $phase:" >&2
    echo "$status" >&2
    return 1
  fi
}

quote_command() {
  printf '%q ' "$@"
  printf '\n'
}

run_command() {
  local name="$1"
  shift
  local log="$LOG_DIR/$name.log"

  echo
  echo "==> $name"
  quote_command "$@"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi

  require_clean_repo "before $name" || return 1

  if command -v timeout >/dev/null 2>&1; then
    timeout "$TIMEOUT_SECONDS" "$@" >"$log" 2>&1
  else
    "$@" >"$log" 2>&1
  fi
  local exit_code=$?

  if [[ "$exit_code" -ne 0 ]]; then
    echo "FAIL $name (exit $exit_code). Log: $log" >&2
    sed -n '1,220p' "$log" >&2
    return "$exit_code"
  fi

  require_clean_repo "after $name" || return 1
  echo "PASS $name. Log: $log"
}

command_for_tool() {
  local tool="$1"
  local prompt="handoff import $BUNDLE. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."
  local codex_prompt="Use the Waybill handoff skill. /handoff import $BUNDLE. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."

  case "$tool" in
    claude)
      COMMAND=(claude -p --permission-mode plan --no-session-persistence "$codex_prompt")
      ;;
    codex)
      COMMAND=(codex exec --ephemeral -s read-only -C "$ROOT" "$codex_prompt")
      ;;
    cursor)
      COMMAND=(agent -p --trust --mode=ask "$prompt")
      ;;
    opencode)
      COMMAND=(opencode run --command handoff "import $BUNDLE. Do not modify files; only read the bundle, verify repository state, and summarize the handoff.")
      ;;
    gemini)
      COMMAND=(gemini --skip-trust --approval-mode plan --model "$GEMINI_MODEL" -p "$prompt")
      ;;
    *)
      echo "Unknown tool: $tool" >&2
      return 2
      ;;
  esac
}

require_tool_binary() {
  local tool="$1"
  local binary="$tool"
  case "$tool" in
    cursor) binary="agent" ;;
    claude) binary="claude" ;;
    codex) binary="codex" ;;
    opencode) binary="opencode" ;;
    gemini) binary="gemini" ;;
  esac
  if ! command -v "$binary" >/dev/null 2>&1; then
    echo "Missing CLI for $tool: $binary" >&2
    return 1
  fi
}

LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/waybill-agent-smoke.XXXXXX")"
echo "Repo: $ROOT"
echo "Bundle: $BUNDLE"
echo "Logs: $LOG_DIR"
echo "Timeout: ${TIMEOUT_SECONDS}s"

if [[ "$DRY_RUN" -eq 0 ]]; then
  require_clean_repo "before smoke tests" || exit 1
fi

for tool in "${TOOLS[@]}"; do
  if [[ "$DRY_RUN" -eq 0 ]]; then
    require_tool_binary "$tool" || exit 1
  fi
  COMMAND=()
  command_for_tool "$tool" || exit 1
  run_command "$tool" "${COMMAND[@]}" || exit 1
done

if [[ "$DRY_RUN" -eq 0 ]]; then
  require_clean_repo "after smoke tests" || exit 1
fi

echo
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run complete."
else
  echo "All requested agent smoke tests passed."
fi
