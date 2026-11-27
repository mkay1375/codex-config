---
name: large-tasks
description: Break coding tasks that are too large to complete well in one pass into subagent parts, with commits between dependent parts and a final integrated review. Use when work needs coordinated multi-part implementation.
---

# Large Tasks

## Split and complete the work

When a task is too big to do well in one pass, split it into parts and work through them:

1. Run each part in a subagent.
2. Commit that part.
3. Move on to the next part and repeat.

Don't start a part that depends on another until that one is committed. Parts that don't
depend on each other can run at the same time: launch their subagents together, then commit
each part as it finishes. Once every part is done,
review the whole change as one piece and fix what the review finds.

## Choose where to work

Before starting, check the current Git branch and identify the repository's main
branch (`main`, or its configured primary branch). If currently on that branch
and the user has not already chosen where to work, ask whether to do this job
on the current branch or in a new branch and worktree. Wait for their answer
before editing files, launching implementation subagents, or committing changes.
Follow their choice; do not create a branch or worktree before they choose it.
An existing instruction to use a new branch and worktree, including invocation
of Do E2E, already supplies that choice; do not ask again.

## Progress updates

Only post updates when there is important information the user needs
to know. Avoid narrating routine steps or tool calls. Keep required
updates brief, and finish with a concise summary of results and verification.
