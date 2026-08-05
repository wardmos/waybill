#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="examples/claude-to-codex"
DRY_RUN=0
TIMEOUT_SECONDS="${WAYBILL_SMOKE_TIMEOUT:-180}"
GEMINI_MODEL="${WAYBILL_GEMINI_MODEL:-}"
CLAUDE_BINARY="${WAYBILL_CLAUDE_BINARY:-claude}"
CODEX_BINARY="${WAYBILL_CODEX_BINARY:-codex}"
CURSOR_BINARY="${WAYBILL_CURSOR_BINARY:-agent}"
OPENCODE_BINARY="${WAYBILL_OPENCODE_BINARY:-opencode}"
GEMINI_BINARY="${WAYBILL_GEMINI_BINARY:-gemini}"
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
  WAYBILL_GEMINI_MODEL        Optional Gemini model. Omit to use the CLI default.
  WAYBILL_CLAUDE_BINARY       Claude Code executable. Defaults to claude.
  WAYBILL_CODEX_BINARY        Codex executable. Defaults to codex.
  WAYBILL_CURSOR_BINARY       Cursor executable. Defaults to agent.
  WAYBILL_OPENCODE_BINARY     OpenCode executable. Defaults to opencode.
  WAYBILL_GEMINI_BINARY       Gemini CLI executable. Defaults to gemini.

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
  local adapter_path
  case "$tool" in
    claude) adapter_path="adapters/claude-code/skills/handoff/SKILL.md" ;;
    codex) adapter_path="adapters/codex/skills/handoff/SKILL.md" ;;
    cursor) adapter_path="adapters/cursor/rules/handoff.mdc" ;;
    opencode) adapter_path="adapters/opencode/skills/handoff/SKILL.md" ;;
    gemini) adapter_path="adapters/gemini-cli/skills/handoff/SKILL.md" ;;
    *) echo "Unknown tool: $tool" >&2; return 2 ;;
  esac
  local prompt="Read $adapter_path and follow its handoff import workflow for $BUNDLE. Do not modify files; only read the bundle, verify repository state, and summarize the handoff."

  case "$tool" in
    claude)
      COMMAND=("$CLAUDE_BINARY" -p --permission-mode plan --no-session-persistence "$prompt")
      ;;
    codex)
      COMMAND=("$CODEX_BINARY" exec --ephemeral -s read-only -C "$ROOT" "$prompt")
      ;;
    cursor)
      COMMAND=("$CURSOR_BINARY" -p --trust --mode=ask "$prompt")
      ;;
    opencode)
      COMMAND=("$OPENCODE_BINARY" run "$prompt")
      ;;
    gemini)
      COMMAND=("$GEMINI_BINARY" --skip-trust --approval-mode plan)
      if [[ -n "$GEMINI_MODEL" ]]; then
        COMMAND+=(--model "$GEMINI_MODEL")
      fi
      COMMAND+=(-p "$prompt")
      ;;
    *)
      echo "Unknown tool: $tool" >&2
      return 2
      ;;
  esac
}

adapter_and_binary_for_tool() {
  local tool="$1"
  case "$tool" in
    claude) ADAPTER="claude-code"; BINARY="$CLAUDE_BINARY" ;;
    codex) ADAPTER="codex"; BINARY="$CODEX_BINARY" ;;
    cursor) ADAPTER="cursor"; BINARY="$CURSOR_BINARY" ;;
    opencode) ADAPTER="opencode"; BINARY="$OPENCODE_BINARY" ;;
    gemini) ADAPTER="gemini-cli"; BINARY="$GEMINI_BINARY" ;;
    *) echo "Unknown tool: $tool" >&2; return 2 ;;
  esac
}

require_tool_binary() {
  local tool="$1"
  adapter_and_binary_for_tool "$tool" || return $?
  if [[ "$BINARY" == */* ]]; then
    if [[ ! -x "$BINARY" ]]; then
      echo "Missing CLI for $tool: $BINARY" >&2
      return 1
    fi
  elif ! command -v "$BINARY" >/dev/null 2>&1; then
    echo "Missing CLI for $tool: $BINARY" >&2
    return 1
  fi
}

verify_tool_identity() {
  local tool="$1"
  adapter_and_binary_for_tool "$tool" || return $?
  local report="$LOG_DIR/$tool-identity.json"
  local identity_command=(
    python3 "$ROOT/scripts/adapter-matrix.py"
    --adapter "$ADAPTER"
    --executable "$ADAPTER=$BINARY"
    --identity-only
  )

  echo
  echo "==> $tool identity"
  quote_command "${identity_command[@]}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi

  if ! "${identity_command[@]}" >"$report"; then
    echo "FAIL $tool executable identity. Report: $report" >&2
    sed -n '1,220p' "$report" >&2
    return 1
  fi
  echo "PASS $tool executable identity. Report: $report"
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
  verify_tool_identity "$tool" || exit 1
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
