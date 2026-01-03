---
description: Start autonomous self-correcting loop until task completion
allowed-tools: Read, Glob, Grep, Edit, Write, Bash(git:*), Bash(npm:*), Bash(python*:*)
argument-hint: <task description>
---

# Ralph Wiggum Autonomous Loop

You are entering an autonomous loop mode that continues until the task is complete.

## Your Task

$ARGUMENTS

## Loop Protocol

### 1. Work Autonomously
- Use all available tools to complete the task
- Make incremental progress each iteration
- Don't wait for approval - take action

### 2. Commit Frequently
- Commit after each meaningful change
- Use clear, descriptive commit messages
- Format: "type: description" (e.g., "fix: resolve null pointer in auth")

### 3. Run Tests
- Execute tests after making changes
- Fix failing tests before proceeding
- Don't leave the codebase in a broken state

### 4. Self-Correct
- If you encounter an error, analyze and try a different approach
- Don't repeat the same failing action
- Document blockers in SHARED_TASK_NOTES.md

### 5. Track Progress
- Update TODO.md if the task is complex
- Mark completed subtasks
- Add new subtasks as discovered

## Completion Signal

When you have **fully completed** the task:
- Verify all changes work correctly
- Ensure tests pass
- Commit any remaining changes
- Output the exact phrase: `TASK_COMPLETE`

**Important:** The signal must appear in 2+ consecutive iterations to stop the loop.

## Error Recovery

If blocked:
1. Document the issue in SHARED_TASK_NOTES.md
2. Try an alternative approach
3. If truly stuck, describe what's needed and output `TASK_BLOCKED`

## Context Persistence

Between iterations, maintain context by:
- Writing notes to `SHARED_TASK_NOTES.md`
- Committing work-in-progress
- Updating TODO.md with progress

---

Begin working on the task now. Remember: work autonomously and output TASK_COMPLETE when done.
