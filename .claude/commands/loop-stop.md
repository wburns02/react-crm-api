---
description: Gracefully stop an autonomous loop session
allowed-tools: Read, Write, Bash(rm:*), Bash(kill:*)
argument-hint: [session-id]
---

# Gracefully Stop Loop

Stop an autonomous loop session cleanly, preserving state.

## Target Session
$ARGUMENTS

## Instructions

1. **Identify Active Sessions**
   - Check for lock files in `~/.claude/ralph-logs/` and `~/.claude/todo-logs/`
   - If session-id provided, target that specific session
   - Otherwise, show active sessions and ask which to stop

2. **Save Current State**
   - Update the state file with status: "stopped_by_user"
   - Preserve iteration count and progress
   - Add stop timestamp

3. **Update Context Files**
   - If SHARED_TASK_NOTES.md exists, add a note about the stop
   - If TODO.md has in-progress items, mark current task appropriately

4. **Remove Lock Files**
   - Remove the lock file for the stopped session
   - Verify no orphaned processes

5. **Report**
   - Confirm session stopped
   - Show what was preserved
   - Provide resume instructions

## Resume Instructions

To resume a stopped session:
```bash
# Using ralph-wiggum runner
./scripts/ralph-wiggum-runner.sh --prompt "Continue previous work" --working-dir .

# Or use the /ralph-loop command with context
/ralph-loop Review SHARED_TASK_NOTES.md and continue from where we left off
```

Now check for active sessions and stop as requested.
