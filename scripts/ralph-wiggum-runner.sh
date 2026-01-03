#!/bin/bash
# Ralph Wiggum Autonomous Loop Runner v2.0
# Runs Claude Code in a self-correcting loop until task completion
# With: structured logging, cost tracking, signal handling, cross-platform support

set -euo pipefail

VERSION="2.0.0"

# Configuration with defaults
COMPLETION_SIGNAL="${RALPH_COMPLETION_SIGNAL:-TASK_COMPLETE}"
COMPLETION_THRESHOLD="${RALPH_COMPLETION_THRESHOLD:-2}"
MAX_ITERATIONS="${RALPH_MAX_ITERATIONS:-50}"
MAX_COST="${RALPH_MAX_COST:-}"
MAX_DURATION="${RALPH_MAX_DURATION:-}"
LOG_DIR="${RALPH_LOG_DIR:-$HOME/.claude/ralph-logs}"
LOG_FORMAT="${RALPH_LOG_FORMAT:-json}"  # json or text

# Runtime state
STATE_FILE=""
LOCK_FILE=""
ITERATION=0
COMPLETION_COUNT=0
TOTAL_COST=0
START_TIME=0
SESSION_ID=""
SESSION_LOG=""
PROMPT=""
WORKING_DIR="."
DRY_RUN=false
CHECK_DEPS=false

# Colors (only used for text format)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

#=============================================================================
# UTILITY FUNCTIONS
#=============================================================================

# Cross-platform ISO date
get_iso_date() {
    date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
    python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())" 2>/dev/null || \
    date +"%Y-%m-%dT%H:%M:%S"
}

# Cross-platform timestamp from epoch
epoch_to_iso() {
    local epoch="$1"
    date -u -d "@$epoch" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
    date -u -r "$epoch" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
    python3 -c "from datetime import datetime, timezone; print(datetime.fromtimestamp($epoch, timezone.utc).isoformat())" 2>/dev/null || \
    echo "unknown"
}

# Escape string for JSON
json_escape() {
    local str="$1"
    printf '%s' "$str" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || \
    printf '%s' "$str" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g; s/\n/\\n/g' | sed ':a;N;$!ba;s/\n/\\n/g'
}

# Structured JSON logging
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

    echo "$log_entry" >> "$SESSION_LOG"

    # Also output to console in readable format
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

log() {
    log_json "INFO" "$1" "${2:-}"
}

log_error() {
    log_json "ERROR" "$1" "${2:-}"
}

log_warn() {
    log_json "WARN" "$1" "${2:-}"
}

log_success() {
    log_json "SUCCESS" "$1" "${2:-}"
}

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

    # Python3 is optional but recommended for cross-platform date handling
    if ! command -v python3 &> /dev/null; then
        log_warn "python3 not found - some cross-platform features may not work"
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
        echo "  - python3: $(python3 --version 2>/dev/null || echo 'not installed (optional)')"
        exit 0
    fi
}

#=============================================================================
# SIGNAL HANDLING & CLEANUP
#=============================================================================

cleanup() {
    local exit_code=$?

    log_warn "Cleanup triggered (exit code: $exit_code)"

    # Remove lock file
    if [ -n "$LOCK_FILE" ] && [ -f "$LOCK_FILE" ]; then
        rm -f "$LOCK_FILE"
    fi

    # Save final state
    if [ -n "$STATE_FILE" ]; then
        save_state "interrupted"
    fi

    # Log final stats
    if [ $ITERATION -gt 0 ]; then
        local elapsed=$(($(date +%s) - START_TIME))
        log "Session ended" "\"total_iterations\":$ITERATION,\"elapsed_seconds\":$elapsed,\"final_status\":\"interrupted\""
    fi

    exit $exit_code
}

setup_signal_handlers() {
    trap cleanup EXIT
    trap 'log_warn "Received SIGINT"; exit 130' INT
    trap 'log_warn "Received SIGTERM"; exit 143' TERM
    trap 'log_warn "Received SIGHUP"; exit 129' HUP
}

#=============================================================================
# FILE LOCKING
#=============================================================================

acquire_lock() {
    LOCK_FILE="$LOG_DIR/.ralph-wiggum.lock"

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
# LIMIT CHECKING
#=============================================================================

check_limits() {
    # Check iteration limit
    if [ "$ITERATION" -ge "$MAX_ITERATIONS" ]; then
        log_warn "Max iterations ($MAX_ITERATIONS) reached"
        return 1
    fi

    # Check duration limit
    if [ -n "$MAX_DURATION" ]; then
        local duration_seconds=0
        local hours=0 minutes=0 seconds=0

        # Parse duration string (e.g., "2h30m", "90m", "1h")
        if [[ "$MAX_DURATION" =~ ([0-9]+)h ]]; then
            hours="${BASH_REMATCH[1]}"
        fi
        if [[ "$MAX_DURATION" =~ ([0-9]+)m ]]; then
            minutes="${BASH_REMATCH[1]}"
        fi
        if [[ "$MAX_DURATION" =~ ([0-9]+)s ]]; then
            seconds="${BASH_REMATCH[1]}"
        fi

        duration_seconds=$((hours * 3600 + minutes * 60 + seconds))

        if [ $duration_seconds -gt 0 ]; then
            local elapsed=$(($(date +%s) - START_TIME))
            if [ "$elapsed" -ge "$duration_seconds" ]; then
                log_warn "Duration limit ($MAX_DURATION / ${duration_seconds}s) reached after ${elapsed}s"
                return 1
            fi
        fi
    fi

    # Check cost limit (if we have cost data)
    if [ -n "$MAX_COST" ] && [ "$TOTAL_COST" != "0" ]; then
        local max_cost_cents
        max_cost_cents=$(echo "$MAX_COST * 100" | bc 2>/dev/null || echo "0")
        local total_cost_cents
        total_cost_cents=$(echo "$TOTAL_COST * 100" | bc 2>/dev/null || echo "0")

        if [ "$total_cost_cents" -ge "$max_cost_cents" ] 2>/dev/null; then
            log_warn "Cost limit (\$$MAX_COST) reached (current: \$$TOTAL_COST)"
            return 1
        fi
    fi

    return 0
}

#=============================================================================
# COMPLETION DETECTION (with word-boundary matching)
#=============================================================================

check_completion() {
    local output="$1"

    # Use word-boundary matching to avoid false positives
    # The signal must appear as a complete word/phrase
    if echo "$output" | grep -qwF "$COMPLETION_SIGNAL"; then
        COMPLETION_COUNT=$((COMPLETION_COUNT + 1))
        log_success "Completion signal detected" "\"count\":$COMPLETION_COUNT,\"threshold\":$COMPLETION_THRESHOLD"

        if [ "$COMPLETION_COUNT" -ge "$COMPLETION_THRESHOLD" ]; then
            return 0
        fi
    else
        if [ $COMPLETION_COUNT -gt 0 ]; then
            log "Completion counter reset (signal not found in this iteration)"
        fi
        COMPLETION_COUNT=0
    fi

    return 1
}

#=============================================================================
# PROMPT BUILDING (with proper escaping)
#=============================================================================

build_prompt() {
    # Escape the completion signal for safe inclusion in prompt
    local safe_signal
    safe_signal=$(printf '%s' "$COMPLETION_SIGNAL" | sed 's/[&/\]/\\&/g')

    if [ "$ITERATION" -eq 0 ]; then
        cat << EOF
$PROMPT

IMPORTANT: When you have fully completed this task, output the exact phrase "$safe_signal" in your response.
The signal must appear $COMPLETION_THRESHOLD consecutive times (across iterations) for the loop to end.
EOF
    else
        cat << EOF
[ITERATION $ITERATION - Continuing previous task]

Original goal: $PROMPT

Review your previous work and continue. If blocked, try a different approach.
When completely finished, output "$safe_signal".
EOF
    fi
}

#=============================================================================
# STATE MANAGEMENT
#=============================================================================

save_state() {
    local status="${1:-running}"
    local started_at
    started_at=$(epoch_to_iso "$START_TIME")
    local now
    now=$(get_iso_date)

    # Use jq for safe JSON generation
    jq -n \
        --arg session "$SESSION_ID" \
        --arg status "$status" \
        --argjson iteration "$ITERATION" \
        --argjson completion_count "$COMPLETION_COUNT" \
        --arg prompt "$PROMPT" \
        --arg working_dir "$WORKING_DIR" \
        --arg started_at "$started_at" \
        --arg last_update "$now" \
        --argjson total_cost "$TOTAL_COST" \
        '{
            session_id: $session,
            status: $status,
            iteration: $iteration,
            completion_count: $completion_count,
            prompt: $prompt,
            working_dir: $working_dir,
            started_at: $started_at,
            last_update: $last_update,
            total_cost: $total_cost
        }' > "$STATE_FILE"
}

#=============================================================================
# COST TRACKING
#=============================================================================

parse_cost_from_output() {
    local output="$1"

    # Try to extract cost from Claude's output (format may vary)
    # Look for patterns like "Cost: $0.05" or "cost: 0.05"
    local cost
    cost=$(echo "$output" | grep -oiE 'cost[:\s]+\$?([0-9]+\.?[0-9]*)' | grep -oE '[0-9]+\.?[0-9]*' | tail -1 || echo "")

    if [ -n "$cost" ]; then
        TOTAL_COST=$(echo "$TOTAL_COST + $cost" | bc 2>/dev/null || echo "$TOTAL_COST")
        log "Cost update" "\"iteration_cost\":$cost,\"total_cost\":$TOTAL_COST"
    fi
}

#=============================================================================
# MAIN LOOP
#=============================================================================

run_loop() {
    log "Starting Ralph Wiggum loop v$VERSION"
    log "Configuration" "\"prompt_length\":${#PROMPT},\"completion_signal\":\"$COMPLETION_SIGNAL\",\"threshold\":$COMPLETION_THRESHOLD,\"max_iterations\":$MAX_ITERATIONS"

    [ -n "$MAX_DURATION" ] && log "Duration limit set" "\"max_duration\":\"$MAX_DURATION\""
    [ -n "$MAX_COST" ] && log "Cost limit set" "\"max_cost\":$MAX_COST"

    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN - would execute Claude Code with above settings"
        return 0
    fi

    cd "$WORKING_DIR" || { log_error "Cannot change to working directory: $WORKING_DIR"; exit 1; }
    log "Working directory" "\"path\":\"$(pwd)\""

    while check_limits; do
        ITERATION=$((ITERATION + 1))
        save_state "running"

        log "=== Starting iteration ===" "\"iteration\":$ITERATION"

        local current_prompt
        current_prompt=$(build_prompt)

        # Run Claude Code and capture output
        local output_file="$LOG_DIR/output_${SESSION_ID}_iter${ITERATION}.txt"
        local exit_code=0

        log "Running Claude Code..."

        # Run claude with the prompt (keeping permissive mode per user preference)
        if claude --dangerously-skip-permissions -p "$current_prompt" 2>&1 | tee "$output_file"; then
            exit_code=0
        else
            exit_code=$?
        fi

        local output
        output=$(cat "$output_file" 2>/dev/null || echo "")
        local output_size=${#output}

        log "Claude execution complete" "\"exit_code\":$exit_code,\"output_size\":$output_size"

        # Parse cost from output
        parse_cost_from_output "$output"

        if [ $exit_code -eq 0 ]; then
            # Check for completion
            if check_completion "$output"; then
                log_success "Task completed successfully!" "\"total_iterations\":$ITERATION,\"total_cost\":$TOTAL_COST"
                save_state "completed"
                rm -f "$LOCK_FILE"
                return 0
            fi
        else
            log_warn "Claude exited with error, will retry..." "\"exit_code\":$exit_code"
        fi

        # Brief pause between iterations
        sleep 2
    done

    log_warn "Loop ended without completion signal" "\"final_iteration\":$ITERATION"
    save_state "limit_reached"
    return 1
}

#=============================================================================
# HELP & ARGUMENT PARSING
#=============================================================================

show_help() {
    cat << EOF
Ralph Wiggum Autonomous Loop Runner v$VERSION

USAGE:
    ralph-wiggum-runner.sh --prompt "your task" [options]

REQUIRED:
    -p, --prompt <text>           The task/prompt for Claude to work on

OPTIONS:
    -c, --completion <signal>     Completion signal phrase (default: TASK_COMPLETE)
    -t, --threshold <num>         Consecutive signals needed to stop (default: 2)
    -m, --max-iterations <num>    Maximum loop iterations (default: 50)
    --max-cost <dollars>          Stop if cost exceeds this amount
    --max-duration <duration>     Stop after duration (e.g., "2h30m", "90m")
    --working-dir <path>          Directory to run in (default: current)
    --log-format <format>         Log format: json or text (default: json)
    --dry-run                     Show what would happen without executing
    --check-deps                  Verify dependencies and exit
    -h, --help                    Show this help message
    -v, --version                 Show version

ENVIRONMENT VARIABLES:
    RALPH_COMPLETION_SIGNAL       Default completion signal
    RALPH_COMPLETION_THRESHOLD    Default threshold
    RALPH_MAX_ITERATIONS          Default max iterations
    RALPH_MAX_COST                Default max cost
    RALPH_MAX_DURATION            Default max duration
    RALPH_LOG_DIR                 Log directory (default: ~/.claude/ralph-logs)
    RALPH_LOG_FORMAT              Log format: json or text

EXAMPLES:
    # Run until tests pass
    ralph-wiggum-runner.sh -p "Fix all failing tests" -c "ALL_TESTS_PASS"

    # Add tests with cost limit
    ralph-wiggum-runner.sh -p "Add unit tests until coverage >90%" --max-cost 10.00

    # Overnight code review
    ralph-wiggum-runner.sh -p "Review and fix code quality issues" --max-duration 8h

    # Check dependencies
    ralph-wiggum-runner.sh --check-deps

EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -p|--prompt)
                PROMPT="$2"
                shift 2
                ;;
            -c|--completion)
                COMPLETION_SIGNAL="$2"
                shift 2
                ;;
            -t|--threshold)
                COMPLETION_THRESHOLD="$2"
                shift 2
                ;;
            -m|--max-iterations)
                MAX_ITERATIONS="$2"
                shift 2
                ;;
            --max-cost)
                MAX_COST="$2"
                shift 2
                ;;
            --max-duration)
                MAX_DURATION="$2"
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
                echo "ralph-wiggum-runner v$VERSION"
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

    # Check dependencies first
    check_dependencies

    # Validate required args
    if [ -z "$PROMPT" ]; then
        echo "Error: --prompt is required"
        show_help
        exit 1
    fi

    # Validate numeric inputs
    if ! [[ "$COMPLETION_THRESHOLD" =~ ^[0-9]+$ ]]; then
        echo "Error: --threshold must be a positive integer"
        exit 1
    fi

    if ! [[ "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
        echo "Error: --max-iterations must be a positive integer"
        exit 1
    fi

    # Setup
    mkdir -p "$LOG_DIR"
    START_TIME=$(date +%s)
    SESSION_ID=$(date +%Y%m%d_%H%M%S)_$$
    SESSION_LOG="$LOG_DIR/session_$SESSION_ID.json"
    STATE_FILE="$LOG_DIR/state_$SESSION_ID.json"

    # Initialize log file
    echo "[]" > "$SESSION_LOG"

    # Acquire lock and setup signal handlers
    acquire_lock
    setup_signal_handlers

    # Run the loop
    run_loop
}

main "$@"
