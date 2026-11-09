# AGENTS.md

## Progress updates

Only post updates when there is important information the user needs
to know. Avoid narrating routine steps or tool calls. Keep required
updates brief, and finish with a concise summary of results and verification.

## UI changes

When changing an application's UI, include screenshots of the updated
UI in your final response whenever possible. Capture the relevant
screens or states so the changes are easy to review. If screenshots
cannot be provided, briefly explain why.

## Large tasks

When a task is too big to do well in one pass, split it into parts and work through them:

1. Run each part in a subagent.
2. Commit that part.
3. Move on to the next part and repeat.

Don't start a part that depends on another until that one is committed. Parts that don't
depend on each other can run at the same time: launch their subagents together, then commit
each part as it finishes. Once every part is done,
review the whole change as one piece and fix what the review finds.

## Marking a PR reviewed

Whenever a PR's code has been reviewed after implementation and any resulting fixes are
committed, verified and pushed, leave a PR comment whose first line is exactly:

```text
Reviewed at <full 40-character SHA of the PR head once the review's fixes are pushed>
```

Follow it with one line saying which review ran, for example
`Codex review against origin/main; critical fixes verified`. Confirm that the remote PR head
equals the reviewed commit before posting the marker. If the review happened before the PR
existed, post the comment right after opening the PR.

For GitHub, write the comment to a temporary file and use
`gh pr comment <n> --body-file <file>`. For GitLab, including self-hosted, post a plain MR note
with `glab api -X POST "projects/:id/merge_requests/<n>/notes" -f body=<text>` using proper
shell quoting and actual newlines. Use a structured API body or file input when supported.

Any later commit on the branch, including a base-branch update, makes the PR unreviewed
again. The `$merge-prs` skill relies on this exact marker to skip PRs already reviewed.

## Optional Doska tracking

Use the `doska-workflow` skill for explicit Doska task requests, or when this
machine's tracking hooks have been deliberately activated. Merely syncing this
repository does not activate tracking. Honor the preflight gate and the user's
choice when Doska is unavailable; never infer permission to continue untracked.
Capture-for-later requests do not authorize task execution.
