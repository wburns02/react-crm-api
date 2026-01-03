---
description: Process all items in TODO.md until complete
allowed-tools: Read, Glob, Grep, Edit, Write, Bash(git:*), Bash(npm:*), Bash(pytest:*)
argument-hint: [optional constraints]
---

# Process All TODO Items

Work through all items in TODO.md sequentially until the list is empty.

## Optional Constraints
$ARGUMENTS

## Protocol

### For Each Task:

1. **Read TODO.md** to find the next pending task (`[ ]` or `[~]`)
2. **Mark as in-progress** by changing `[ ]` to `[~]`
3. **Complete the task** using appropriate tools
4. **Verify the work** (run tests if applicable)
5. **Mark as complete** by changing `[~]` to `[x]`
6. **Commit changes** with message: "Complete: <task summary>"
7. **Repeat** until no pending tasks remain

### Task Processing Order

1. Process `PRIORITY:HIGH` items first
2. Resume `[~]` in-progress items
3. Then process `[ ]` pending items in order
4. Skip items marked with `BLOCKED:`

### Task Format Reference

```markdown
- [ ] Pending task
- [~] In-progress task
- [x] Completed task
- [ ] PRIORITY:HIGH - Urgent task
- [ ] Task BLOCKED: reason
```

### Handling Subtasks

Parent tasks with subtasks:
```markdown
- [ ] Parent task
  - [ ] Subtask 1
  - [ ] Subtask 2
```

Complete all subtasks before marking parent complete.

### If a Task Cannot Be Completed

1. Add `BLOCKED: <reason>` to the task line
2. Document details in the Notes section of TODO.md
3. Move to the next actionable task
4. Continue processing

### Completion

When all tasks in TODO.md are marked `[x]`:
1. Move completed tasks to the "Completed Tasks" section (if it exists)
2. Update the timestamp at the bottom of TODO.md
3. Output: `ALL_TODOS_COMPLETE`

---

Now read TODO.md and begin processing. Start with the first high-priority or in-progress item.
