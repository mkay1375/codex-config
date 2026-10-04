---
name: e2e-worktree
description: Explicitly invoked workflow to complete a coding task in a new Git worktree, commit all task changes, review and fix critical issues, push the branch, and deliver a GitHub PR or GitLab MR link.
---

# E2E Worktree

Use only when explicitly invoked. Take the accompanying task through implementation and
deliver a reviewable PR. Invocation authorizes creating a worktree and branch, committing
the task's changes, pushing that branch, opening the PR, and posting its review marker.
Continue through these steps without asking for confirmation again. It does not authorize
merging, deploying, or deleting existing branches or worktrees. If no task or repository can
be identified from the conversation and workspace, ask for the missing information.

## 1. Start in a new worktree

- Read applicable repository instructions. Inspect Git status, remotes, existing worktrees,
  and the intended PR base before making changes. Preserve the user's existing checkout,
  including its staged and uncommitted work; do not stash, reset, or carry it into the new
  worktree unless the task explicitly requires those changes.
- Identify the hosting service and authenticated CLI/API. Use `gh` for GitHub or `glab` for
  GitLab, including self-hosted instances. Select the repository and host explicitly when
  CLI defaults could target another repository. Report missing authentication or permissions
  accurately; continue independent local work when useful.
- Use the requested base branch, otherwise the repository's established integration branch
  or remote default branch. Fetch it before branching. If the task explicitly builds on an
  existing feature branch, use that starting point and preserve the intended PR target.
- Create a unique task branch and a new worktree at a writable path with
  `git worktree add -b <task-branch> <absolute-worktree-path> <starting-ref>`.
  Avoid branch or directory collisions. Run all task edits, Git commands, and checks in that
  worktree; record its path, branch, base reference, remote, and push destination.

## 2. Implement and commit everything for the task

Complete the requested behavior and repository-required checks. For large tasks, follow
applicable AGENTS.md delegation and commit requirements: run each part in a subagent and
commit it before starting dependent parts. Give each agent an explicit worktree path;
use separate worktrees if edits could overlap, then integrate their commits into the task
branch before reviewing the whole change.

Inspect the full diff and untracked files, then commit all task changes, including new files
and deletions. "Everything" means work produced for this task, excluding unrelated user
changes, credentials, temporary review files, and generated artifacts the repository does
not track. Stage only after checking that scope. Do not create empty commits when no change
is needed. Before review, ensure every intended task change is committed and the worktree
is clean apart from understood ignored artifacts.

## 3. Review and fix critical issues

Review the complete branch diff against the fetched PR base, including all part commits.
Use Codex's built-in review when available, for example from the worktree:

```bash
codex review -c model_reasoning_effort='"high"' --base <base-ref>
```

If that capability is unavailable, perform an explicit code review of the same diff and
report which review actually ran. Review reports findings; implement fixes separately.
Prioritize concrete correctness bugs, security vulnerabilities, data loss, broken builds
or tests, migration failures, and integration breaks. Fix critical findings; avoid unrelated
style changes. Ask only when a blocking fix requires a material user decision.

Verify fixes with relevant checks and commit them. Review the final combined diff again,
including the fixes, and rerun checks affected by those fixes. Repeat until critical findings
introduced by this change are resolved. Do not claim a completed review or successful checks
when they did not run. If a blocker cannot be resolved, preserve the work and explain it;
if publishing a useful incomplete change, clearly label the PR as a draft and disclose the
blocker instead of posting a completed review marker.

## 4. Push and open the PR

- Inspect final status and commits. Record the full reviewed HEAD SHA, then push the new
  branch to its intended destination with upstream tracking. Never force-push or overwrite
  an unrelated remote branch. If rejected, inspect why and resolve only within authorized
  scope; any new commit requires renewed review and verification.
- Create the PR against the intended base. Use `gh pr create` on GitHub or `glab mr create`
  on GitLab with explicit source/target branches and repository as needed. Check for an
  existing request for this branch before retrying creation to avoid duplicates.
- Write a concise title and description explaining the problem, resulting behavior,
  validation actually performed, and any limitations. For multiline CLI bodies, use a
  temporary file and `--body-file` when supported, or a structured API body with actual
  newlines. Keep temporary files outside the repository.
- Confirm the request exists on the intended repository and targets the intended branch.
  Report observed CI status accurately; fix failures caused by this change. After any fix,
  repeat the relevant checks and review, commit, and push before recording review evidence.

## 5. Mark the exact remote head reviewed

After opening the PR, fetch its remote head through the hosting service. It must equal the
full 40-character SHA reviewed and verified locally. Post a comment whose first line is
exactly:

```text
Reviewed at <full 40-character SHA of the PR head>
```

Follow it with one line naming the actual review, for example
`Codex review against origin/main; critical fixes verified`.
On GitHub, write the two lines to a temporary file and use
`gh pr comment <n> --body-file <file>`. On GitLab, post a plain MR note through
`glab api -X POST "projects/:id/merge_requests/<n>/notes" -f body=<text>` with proper shell
quoting and actual newlines, or use a structured API body/file input when supported.

Any later commit, including a base update, invalidates the marker. If the remote head differs,
review and verify the actual updated branch before posting a new marker. Stop and report
repeated concurrent changes instead of certifying a moving head or overwriting others' work.

## 6. Give the user the PR

Lead the final response with the clickable PR/MR link. Briefly state what changed, critical
fixes if any, validation results, and pending or failed checks. Include the worktree path and
branch so the user can continue locally. Preserve the worktree and branch unless cleanup is
explicitly requested. If push or PR creation failed, report the concrete blocker and saved
local work; never invent a link or imply the workflow completed.
