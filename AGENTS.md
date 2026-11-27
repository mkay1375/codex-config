# AGENTS.md

## Progress updates

Only post updates when there is important information the user needs
to know. Avoid narrating routine steps or tool calls. Keep required
updates brief, and finish with a concise summary of results and verification.

## Large tasks

When a task is too big to do well in one pass, split it into parts and work through them:

1. Run each part in a subagent.
2. Commit that part.
3. Move on to the next part and repeat.

Don't start a part that depends on another until that one is committed. Parts that don't
depend on each other can run at the same time: launch their subagents together, then commit
each part as it finishes. Once every part is done,
review the whole change as one piece and fix what the review finds.

If RTK.md exists in the same directory as this AGENTS.md,
read it and follow its instructions. Otherwise, skip it.
