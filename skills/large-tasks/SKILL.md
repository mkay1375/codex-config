---
name: large-tasks
description: Break coding tasks that are too large to complete well in one pass into subagent parts, with commits between dependent parts and a final integrated review. Use when work needs coordinated multi-part implementation.
---

# Large Tasks

When a task is too big to do well in one pass, split it into parts and work through them:

1. Run each part in a subagent.
2. Commit that part.
3. Move on to the next part and repeat.

Don't start a part that depends on another until that one is committed. Parts that don't
depend on each other can run at the same time: launch their subagents together, then commit
each part as it finishes. Once every part is done,
review the whole change as one piece and fix what the review finds.
