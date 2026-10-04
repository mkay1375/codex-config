# AGENTS.md

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
