#!/bin/bash
# TODO-Driven Autonomous Loop Runner v2.0
# Processes TODO.md items until all are complete
# With: structured logging, file locking, cross-platform support

set -euo pipefail

VERSION="2.0.0"

TODO_FILE="${TODO_FILE:-TODO.md}"
COMPLETION_SIGNAL="ALL_TODOS_COMPLETE"
MAX_ITERATIONS="${TODO_MAX_ITERATIONS:-100}"
LOG_DIR="${TODO_LOG_DIR:-$HOME/.claude/todo-logs}"
LOG_FORMAT="${TODO_LOG_FORMAT:-json}"

# Runtime state
LOCK_FILE=""
SESSION_ID=""
SESSION_LOG=""
WORKING_DIR="."
DRY_RUN=false
CHECK_DEPS=false
START_TIME=0
ITERATION=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

#=============================================================================
# UTILITY FUNCTIONS
#=============================================================================

get_iso_date() {
    date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
    python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())" 2>/dev/null || \
    date +"%Y-%m-%dT%H:%M:%S"
}

json_escape() {
    local str="$1"
    printf '%s' "$str" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || \
    printf '%s' "$str" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g'
}

log_json() {
    local level="$1"
    local message="$2"
    local extra="${3:-}"

    local timestamp
    timestamp=$(get_iso_date)

    local json_msg
    json_msg=$(json_escape "$message")

    local log_entry
    if [ -n "$extra" ]; then
        log_entry="{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":$json_msg,\"session\":\"$SESSION_ID\",\"iteration\":$ITERATION,$extra}"
    else
        log_entry="{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":$json_msg,\"session\":\"$SESSION_ID\",\"iteration\":$ITERATION}"
    fi

    [ -n "$SESSION_LOG" ] && echo "$log_entry" >> "$SESSION_LOG"

    if [ "$LOG_FORMAT" = "json" ]; then
        echo "$log_entry"
    else
        local color=""
        case "$level" in
            ERROR) color="$RED" ;;
            WARN)  color="$YELLOW" ;;
            INFO)  color="$BLUE" ;;
            SUCCESS) color="$GREEN" ;;
        esac
        echo -e "${color}[$timestamp] [$level] $message${NC}"
    fi
}

log() { log_json "INFO" "$1" "${2:-}"; }
log_error() { log_json "ERROR" "$1" "${2:-}"; }
log_warn() { log_json "WARN" "$1" "${2:-}"; }
log_success() { log_json "SUCCESS" "$1" "${2:-}"; }

#=============================================================================
# DEPENDENCY CHECKING
#=============================================================================

check_dependencies() {
    local missing=()

    if ! command -v claude &> /dev/null; then
        missing+=("claude (Claude Code CLI)")
    fi

    if ! command -v jq &> /dev/null; then
        missing+=("jq (JSON processor)")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo "Missing required dependencies:"
        for dep in "${missing[@]}"; do
            echo "  - $dep"
        done
        exit 1
    fi

    if [ "$CHECK_DEPS" = true ]; then
        echo "All dependencies satisfied:"
        echo "  - claude: $(claude --version 2>/dev/null | head -1 || echo 'installed')"
        echo "  - jq: $(jq --version 2>/dev/null || echo 'installed')"
        exit 0
    fi
}

#=============================================================================
# SIGNAL HANDLING & CLEANUP
#=============================================================================

cleanup() {
    local exit_code=$?

    if [ -n "$LOCK_FILE" ] && [ -f "$LOCK_FILE" ]; then
        rm -f "$LOCK_FILE"
    fi

    if [ $ITERATION -gt 0 ]; then
        local elapsed=$(($(date +%s) - START_TIME))
        log "Session ended" "\"total_iterations\":$ITERATION,\"elapsed_seconds\":$elapsed"
    fi

    exit $exit_code
}

setup_signal_handlers() {
    trap cleanup EXIT
    trap 'log_warn "Received SIGINT"; exit 130' INT
    trap 'log_warn "Received SIGTERM"; exit 143' TERM
}

#=============================================================================
# FILE LOCKING
#=============================================================================

acquire_lock() {
    LOCK_FILE="$LOG_DIR/.todo-loop.lock"

    if [ -f "$LOCK_FILE" ]; then
        local pid
        pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            log_error "Another instance is running (PID: $pid)"
            exit 1
        else
            log_warn "Stale lock file found, removing"
            rm -f "$LOCK_FILE"
        fi
    fi

    echo $$ > "$LOCK_FILE"
}

#=============================================================================
# TODO PARSING (improved regex patterns)
#=============================================================================

count_pending_todos() {
    # Match "- [ ]" with optional leading whitespace (handles subtasks)
    local count
    count=$(grep -cE '^[[:space:]]*-[[:space:]]+\[[[:space:]]\]' "$TODO_FILE" 2>/dev/null) || count=0
    printf '%d' "${count:-0}"
}

count_completed_todos() {
    local count
    count=$(grep -cE '^[[:space:]]*-[[:space:]]+\[x\]' "$TODO_FILE" 2>/dev/null) || count=0
    printf '%d' "${count:-0}"
}

count_in_progress_todos() {
    local count
    count=$(grep -cE '^[[:space:]]*-[[:space:]]+\[~\]' "$TODO_FILE" 2>/dev/null) || count=0
    printf '%d' "${count:-0}"
}

get_next_todo() {
    # Priority order:
    # 1. High priority pending items
    # 2. In-progress items (resume)
    # 3. Regular pending items

    local high_priority
    high_priority=$(grep -m1 -E 'PRIORITY:HIGH.*\[[[:space:]]\]|\[[[:space:]]\].*PRIORITY:HIGH' "$TODO_FILE" 2>/dev/null || echo "")

    if [ -n "$high_priority" ]; then
        echo "$high_priority"
        return
    fi

    local in_progress
    in_progress=$(grep -m1 -E '^[[:space:]]*-[[:space:]]+\[~\]' "$TODO_FILE" 2>/dev/null || echo "")

    if [ -n "$in_progress" ]; then
        echo "$in_progress"
        return
    fi

    # Get first pending item (not blocked)
    grep -m1 -E '^[[:space:]]*-[[:space:]]+\[[[:space:]]\]' "$TODO_FILE" 2>/dev/null | grep -v 'BLOCKED:' || echo ""
}

validate_todo_file() {
    if [ ! -f "$TODO_FILE" ]; then
        log_error "TODO file not found: $TODO_FILE"
        return 1
    fi

    # Check for valid TODO format
    if ! grep -qE '^[[:space:]]*-[[:space:]]+\[' "$TODO_FILE"; then
        log_warn "No valid TODO items found in $TODO_FILE"
        log "Expected format: '- [ ] Task description' or '- [x] Completed task'"
        return 1
    fi

    return 0
}

#=============================================================================
# STATE MANAGEMENT
#=============================================================================

save_state() {
    local state_file="$LOG_DIR/state_$SESSION_ID.json"
    local pending completed in_progress

    pending=$(count_pending_todos)
    completed=$(count_completed_todos)
    in_progress=$(count_in_progress_todos)

    jq -n \
        --arg session "$SESSION_ID" \
        --arg todo_file "$TODO_FILE" \
        --argjson iteration "$ITERATION" \
        --argjson pending "$pending" \
        --argjson completed "$completed" \
        --argjson in_progress "$in_progress" \
        --arg last_update "$(get_iso_date)" \
        '{
            session_id: $session,
            todo_file: $todo_file,
            iteration: $iteration,
            pending: $pending,
            completed: $completed,
            in_progress: $in_progress,
            last_update: $last_update
        }' > "$state_file"
}

#=============================================================================
# MAIN LOOP
#=============================================================================

run_loop() {
    if ! validate_todo_file; then
        return 1
    fi

    local pending completed

    pending=$(count_pending_todos)
    completed=$(count_completed_todos)

    log "Starting TODO-driven loop v$VERSION"
    log "TODO file: $TODO_FILE" "\"pending\":$pending,\"completed\":$completed"
    log "Max iterations: $MAX_ITERATIONS"

    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN - showing next task:"
        local next
        next=$(get_next_todo)
        if [ -n "$next" ]; then
            echo "$next"
        else
            echo "No pending tasks"
        fi
        return 0
    fi

    while [ "$ITERATION" -lt "$MAX_ITERATIONS" ]; do
        ITERATION=$((ITERATION + 1))
        save_state

        pending=$(count_pending_todos)
        if [ "$pending" -eq 0 ]; then
            log_success "All TODOs complete!"
            return 0
        fi

        local next_task
        next_task=$(get_next_todo)

        if [ -z "$next_task" ]; then
            log_warn "No actionable tasks found (all may be blocked)"
            return 1
        fi

        log "=== Iteration $ITERATION ===" "\"pending\":$pending"
        log "Processing task" "\"task\":$(json_escape "$next_task")"

        # Build prompt for Claude
        local prompt
        prompt=$(cat << EOF
Process the next TODO item from $TODO_FILE.

Current task: $next_task

Follow the /todo-all protocol:
1. Mark this task as in-progress by changing [ ] to [~]
2. Complete the task (implement, test, verify)
3. Mark as complete by changing [~] to [x]
4. Commit changes with message: "Complete: <task summary>"
5. If blocked, add "BLOCKED: <reason>" and move to next task

When ALL tasks are complete, output: $COMPLETION_SIGNAL
EOF
)

        local output_file="$LOG_DIR/output_${SESSION_ID}_iter${ITERATION}.txt"
        local exit_code=0

        log "Running Claude Code..."

        if claude --dangerously-skip-permissions -p "$prompt" 2>&1 | tee "$output_file"; then
            exit_code=0
        else
            exit_code=$?
        fi

        local output
        output=$(cat "$output_file" 2>/dev/null || echo "")

        log "Claude execution complete" "\"exit_code\":$exit_code,\"output_size\":${#output}"

        # Check for completion signal (word-boundary match)
        if echo "$output" | grep -qwF "$COMPLETION_SIGNAL"; then
            log_success "All TODOs marked complete!" "\"total_iterations\":$ITERATION"
            return 0
        fi

        if [ $exit_code -ne 0 ]; then
            log_warn "Claude exited with error" "\"exit_code\":$exit_code"
        fi

        sleep 2
    done

    pending=$(count_pending_todos)
    log_warn "Max iterations reached" "\"remaining_tasks\":$pending"
    return 1
}

#=============================================================================
# HELP & ARGUMENT PARSING
#=============================================================================

show_help() {
    cat << EOF
TODO-Driven Autonomous Loop Runner v$VERSION

USAGE:
    todo-loop-runner.sh [options]

OPTIONS:
    -f, --file <path>             Path to TODO.md file (default: TODO.md)
    -m, --max-iterations <num>    Maximum iterations (default: 100)
    --working-dir <path>          Working directory (default: current)
    --log-format <format>         Log format: json or text (default: json)
    --dry-run                     Show next task without executing
    --check-deps                  Verify dependencies and exit
    -h, --help                    Show this help
    -v, --version                 Show version

ENVIRONMENT VARIABLES:
    TODO_FILE                     Default TODO file path
    TODO_MAX_ITERATIONS           Default max iterations
    TODO_LOG_DIR                  Log directory
    TODO_LOG_FORMAT               Log format: json or text

TODO FILE FORMAT:
    - [ ] Pending task
    - [~] In-progress task
    - [x] Completed task
    - [ ] PRIORITY:HIGH - Urgent task (processed first)
    - [ ] Task BLOCKED: reason (skipped)

EXAMPLES:
    # Process all todos in current directory
    todo-loop-runner.sh

    # Use specific todo file
    todo-loop-runner.sh -f path/to/TASKS.md

    # Limit iterations
    todo-loop-runner.sh -m 20

    # Check dependencies
    todo-loop-runner.sh --check-deps

EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--file)
                TODO_FILE="$2"
                shift 2
                ;;
            -m|--max-iterations)
                MAX_ITERATIONS="$2"
                shift 2
                ;;
            --working-dir)
                WORKING_DIR="$2"
                shift 2
                ;;
            --log-format)
                LOG_FORMAT="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --check-deps)
                CHECK_DEPS=true
                shift
                ;;
            -v|--version)
                echo "todo-loop-runner v$VERSION"
                exit 0
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

#=============================================================================
# MAIN
#=============================================================================

main() {
    parse_args "$@"

    check_dependencies

    # Validate inputs
    if ! [[ "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
        echo "Error: --max-iterations must be a positive integer"
        exit 1
    fi

    # Setup
    mkdir -p "$LOG_DIR"
    START_TIME=$(date +%s)
    SESSION_ID=$(date +%Y%m%d_%H%M%S)_$$
    SESSION_LOG="$LOG_DIR/session_$SESSION_ID.json"

    cd "$WORKING_DIR" || { echo "Cannot change to directory: $WORKING_DIR"; exit 1; }

    # Acquire lock and setup signal handlers
    acquire_lock
    setup_signal_handlers

    # Run the loop
    run_loop
}

main "$@"
