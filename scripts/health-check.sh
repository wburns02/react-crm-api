#!/bin/bash
# Autonomous Claude Health Check v1.0
# Verifies all dependencies, permissions, and state file integrity

set -euo pipefail

VERSION="1.0.0"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

#=============================================================================
# OUTPUT FUNCTIONS
#=============================================================================

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

print_ok() {
    echo -e "  ${GREEN}[OK]${NC} $1"
}

print_warn() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
    WARNINGS=$((WARNINGS + 1))
}

print_error() {
    echo -e "  ${RED}[ERROR]${NC} $1"
    ERRORS=$((ERRORS + 1))
}

print_info() {
    echo -e "  ${BLUE}[INFO]${NC} $1"
}

#=============================================================================
# DEPENDENCY CHECKS
#=============================================================================

check_dependencies() {
    print_header "Checking Dependencies"

    # Claude CLI
    if command -v claude &> /dev/null; then
        local version
        version=$(claude --version 2>/dev/null | head -1 || echo "unknown")
        print_ok "Claude Code CLI: $version"
    else
        print_error "Claude Code CLI not found"
    fi

    # jq
    if command -v jq &> /dev/null; then
        print_ok "jq: $(jq --version 2>/dev/null || echo 'installed')"
    else
        print_error "jq not found (required for JSON processing)"
    fi

    # Git
    if command -v git &> /dev/null; then
        print_ok "git: $(git --version 2>/dev/null | head -1)"
    else
        print_warn "git not found (recommended for version control)"
    fi

    # Python3
    if command -v python3 &> /dev/null; then
        print_ok "python3: $(python3 --version 2>/dev/null)"
    else
        print_warn "python3 not found (optional, helps with cross-platform compatibility)"
    fi

    # bc (for cost calculations)
    if command -v bc &> /dev/null; then
        print_ok "bc: installed"
    else
        print_warn "bc not found (optional, used for cost calculations)"
    fi

    # gh CLI
    if command -v gh &> /dev/null; then
        print_ok "gh (GitHub CLI): $(gh --version 2>/dev/null | head -1)"
    else
        print_warn "gh (GitHub CLI) not found (optional, used for PR workflows)"
    fi
}

#=============================================================================
# CONFIGURATION CHECKS
#=============================================================================

check_configuration() {
    print_header "Checking Configuration"

    local config_dir="$HOME/.claude"
    local project_config=".claude"

    # Check user config directory
    if [ -d "$config_dir" ]; then
        print_ok "User config directory exists: $config_dir"
    else
        print_warn "User config directory not found: $config_dir"
    fi

    # Check project config
    if [ -d "$project_config" ]; then
        print_ok "Project config directory exists: $project_config"

        # Check settings.json
        if [ -f "$project_config/settings.json" ]; then
            if jq empty "$project_config/settings.json" 2>/dev/null; then
                print_ok "settings.json is valid JSON"

                # Check for hooks
                if jq -e '.hooks.Stop' "$project_config/settings.json" &>/dev/null; then
                    print_ok "Stop hooks configured"
                else
                    print_warn "No Stop hooks configured (recommended for autonomous loops)"
                fi
            else
                print_error "settings.json is invalid JSON"
            fi
        else
            print_warn "No settings.json found in project"
        fi

        # Check commands directory
        if [ -d "$project_config/commands" ]; then
            local cmd_count
            cmd_count=$(find "$project_config/commands" -name "*.md" 2>/dev/null | wc -l)
            print_ok "Commands directory exists ($cmd_count commands)"
        else
            print_warn "No commands directory found"
        fi
    else
        print_warn "No project config directory found (.claude/)"
    fi
}

#=============================================================================
# SCRIPTS CHECKS
#=============================================================================

check_scripts() {
    print_header "Checking Scripts"

    local scripts_dir="scripts"

    if [ -d "$scripts_dir" ]; then
        print_ok "Scripts directory exists"

        # Check each script
        for script in "$scripts_dir"/*.sh; do
            if [ -f "$script" ]; then
                local name
                name=$(basename "$script")

                if [ -x "$script" ]; then
                    # Check for shebang
                    if head -1 "$script" | grep -q '^#!/'; then
                        print_ok "$name (executable, valid shebang)"
                    else
                        print_warn "$name (executable but no shebang)"
                    fi
                else
                    print_warn "$name (not executable - run: chmod +x $script)"
                fi
            fi
        done

        # Check Python scripts
        for script in "$scripts_dir"/*.py; do
            if [ -f "$script" ]; then
                local name
                name=$(basename "$script")

                if python3 -m py_compile "$script" 2>/dev/null; then
                    print_ok "$name (valid Python syntax)"
                else
                    print_error "$name (Python syntax error)"
                fi
            fi
        done
    else
        print_warn "Scripts directory not found"
    fi
}

#=============================================================================
# STATE FILES CHECKS
#=============================================================================

check_state_files() {
    print_header "Checking State Files"

    local log_dirs=(
        "$HOME/.claude/ralph-logs"
        "$HOME/.claude/todo-logs"
        "$HOME/.claude/orchestrator-logs"
    )

    for dir in "${log_dirs[@]}"; do
        if [ -d "$dir" ]; then
            local file_count
            file_count=$(find "$dir" -type f 2>/dev/null | wc -l)

            # Check for lock files
            local lock_files
            lock_files=$(find "$dir" -name "*.lock" 2>/dev/null | wc -l)

            if [ "$lock_files" -gt 0 ]; then
                print_warn "$dir: $file_count files, $lock_files active lock(s)"

                # Check if lock owners are still running
                for lock in "$dir"/*.lock; do
                    if [ -f "$lock" ]; then
                        local pid
                        pid=$(cat "$lock" 2>/dev/null || echo "")
                        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                            print_info "Lock held by running process PID $pid"
                        else
                            print_warn "Stale lock file: $lock (owner not running)"
                        fi
                    fi
                done
            else
                print_ok "$dir: $file_count files, no locks"
            fi

            # Check disk usage
            local size
            size=$(du -sh "$dir" 2>/dev/null | cut -f1)
            print_info "Disk usage: $size"
        else
            print_info "$dir: not created yet"
        fi
    done
}

#=============================================================================
# TODO.md CHECK
#=============================================================================

check_todo_file() {
    print_header "Checking TODO.md"

    if [ -f "TODO.md" ]; then
        print_ok "TODO.md exists"

        local pending completed in_progress blocked

        pending=$(grep -cE '^[[:space:]]*-[[:space:]]+\[[[:space:]]\]' TODO.md 2>/dev/null || echo "0")
        completed=$(grep -cE '^[[:space:]]*-[[:space:]]+\[x\]' TODO.md 2>/dev/null || echo "0")
        in_progress=$(grep -cE '^[[:space:]]*-[[:space:]]+\[~\]' TODO.md 2>/dev/null || echo "0")
        blocked=$(grep -c 'BLOCKED:' TODO.md 2>/dev/null || echo "0")

        print_info "Pending: $pending, In-progress: $in_progress, Completed: $completed, Blocked: $blocked"

        if [ "$in_progress" -gt 1 ]; then
            print_warn "Multiple tasks marked as in-progress"
        fi
    else
        print_info "TODO.md not found (optional)"
    fi
}

#=============================================================================
# CONTINUOUS CLAUDE CHECK
#=============================================================================

check_continuous_claude() {
    print_header "Checking Continuous Claude"

    local cc_path="$HOME/.local/bin/continuous-claude"

    if [ -x "$cc_path" ]; then
        local version
        version=$("$cc_path" --version 2>/dev/null || echo "unknown")
        print_ok "continuous-claude installed: $version"
    elif [ -f "continuous-claude/continuous_claude.sh" ]; then
        print_ok "continuous-claude available locally"
    else
        print_warn "continuous-claude not installed"
        print_info "Install with: curl -fsSL https://raw.githubusercontent.com/AnandChowdhary/continuous-claude/main/install.sh | bash"
    fi
}

#=============================================================================
# ENVIRONMENT CHECK
#=============================================================================

check_environment() {
    print_header "Checking Environment"

    # Check shell
    print_info "Shell: $SHELL"
    print_info "Bash version: ${BASH_VERSION:-unknown}"

    # Check if we're in a git repo
    if git rev-parse --is-inside-work-tree &>/dev/null; then
        local branch
        branch=$(git branch --show-current 2>/dev/null || echo "unknown")
        local status
        status=$(git status --porcelain 2>/dev/null | wc -l)
        print_ok "Git repository (branch: $branch, $status uncommitted changes)"
    else
        print_info "Not in a git repository"
    fi

    # Check ANTHROPIC_API_KEY
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        print_ok "ANTHROPIC_API_KEY is set"
    else
        print_warn "ANTHROPIC_API_KEY not set (may be required for API access)"
    fi
}

#=============================================================================
# SUMMARY
#=============================================================================

print_summary() {
    print_header "Summary"

    if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
        echo -e "\n${GREEN}All checks passed!${NC}"
        echo "The autonomous Claude framework is ready to use."
    elif [ $ERRORS -eq 0 ]; then
        echo -e "\n${YELLOW}Checks completed with $WARNINGS warning(s)${NC}"
        echo "The framework should work, but consider addressing the warnings."
    else
        echo -e "\n${RED}Checks completed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
        echo "Please fix the errors before using the framework."
    fi

    echo ""
}

#=============================================================================
# MAIN
#=============================================================================

show_help() {
    cat << EOF
Autonomous Claude Health Check v$VERSION

USAGE:
    health-check.sh [options]

OPTIONS:
    -h, --help      Show this help
    -v, --version   Show version
    --json          Output results as JSON

CHECKS PERFORMED:
    - Required dependencies (claude, jq)
    - Optional dependencies (git, python3, gh, bc)
    - Configuration files (settings.json, commands)
    - Script validity and permissions
    - State files and lock status
    - TODO.md status
    - continuous-claude installation
    - Environment variables

EOF
}

main() {
    local json_output=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--version)
                echo "health-check v$VERSION"
                exit 0
                ;;
            --json)
                json_output=true
                shift
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    echo -e "${BLUE}Autonomous Claude Health Check v$VERSION${NC}"
    echo "======================================"

    check_dependencies
    check_configuration
    check_scripts
    check_state_files
    check_todo_file
    check_continuous_claude
    check_environment
    print_summary

    exit $ERRORS
}

main "$@"
