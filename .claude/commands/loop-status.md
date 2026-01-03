---
description: Check the status of autonomous loop sessions
allowed-tools: Read, Bash(ls:*), Bash(cat:*), Bash(find:*)
---

# Check Loop Status

Display the current status of autonomous loop sessions.

## Instructions

Check and report on:

1. **Active Lock Files**
   - Check `~/.claude/ralph-logs/.ralph-wiggum.lock`
   - Check `~/.claude/todo-logs/.todo-loop.lock`
   - Report if any processes are currently running

2. **Recent Session Logs**
   - Find the most recent session files in:
     - `~/.claude/ralph-logs/`
     - `~/.claude/todo-logs/`
   - Report last activity timestamp

3. **Current State Files**
   - Read any `state_*.json` files
   - Report: session ID, iteration count, status, completion progress

4. **TODO.md Status** (if exists)
   - Count pending `[ ]` items
   - Count in-progress `[~]` items
   - Count completed `[x]` items
   - Count blocked items

5. **SHARED_TASK_NOTES.md** (if exists)
   - Show current focus and last update

## Output Format

```
=== Autonomous Loop Status ===

Ralph Wiggum:
  Status: [running|idle|completed|interrupted]
  Session: <id>
  Iteration: N
  Completion: N/threshold

TODO Loop:
  Status: [running|idle|completed]
  Pending: N tasks
  In-progress: N tasks
  Completed: N tasks

Last Activity: <timestamp>
```

Now check the status and report findings.
