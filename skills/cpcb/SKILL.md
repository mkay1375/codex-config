---
name: cpcb
description: Commit and push the current task's changes on the current Git branch when explicitly invoked.
---

# Commit and push in current branch

Treat `$cpcb` as authorization to commit and push the current task's changes on the branch already checked out.

- Inspect repository instructions, the current branch, working tree, staged changes, and upstream before acting. Keep the current branch; do not create or switch branches or worktrees. If HEAD is detached, ask which branch to use.
- Review the diff and run checks appropriate to the changes. Stage the current task's files explicitly, including relevant new files. Preserve unrelated edits and staged changes; if ownership is unclear, ask before including them.
- Create a commit with a concise message describing the change. Respect a message supplied by the user. Do not amend existing commits unless requested. If there is nothing new to commit, push any existing unpushed commits on the current branch.
- Push to the current branch's upstream. If no upstream exists and the intended remote is unambiguous, push with `git push -u <remote> <current-branch>`. Ask only when the destination is ambiguous. Never force-push; stop and report a rejection or divergence rather than rewriting history.
- Verify the remote branch head matches the local commit. Report the branch, commit, push result, and checks performed. Do not open a pull request unless requested.
