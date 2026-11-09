# Task workflow

Run one direct invocation of `python3 "$CODEX_HOME/skills/doska-workflow/scripts/doska_flow.py" ...`
(`python` on Windows). Resolve CODEX_HOME to the actual absolute directory first;
when a tool gate is active it deliberately rejects shell variable expansion,
wrappers, pipelines, substitutions, command chains, and arbitrary `python -c`.
Use a single direct command with the literal absolute script path. Quotes around
paths and normal arguments are supported. Do not evade the gate with another tool.

## Capture and start

```text
capture "Investigate Android app" --project github.com/example/repo --state Procrastinated --session SESSION --acceptance "A feasibility report" --participant "Alex" --reconsider-on 2026-12-01
begin TASK_UUID --session SESSION --turn TURN
finish TASK_UUID --session SESSION --state Review --summary "Report ready" --verification "Source inspected; no device build"
```

All examples name proposed operations, not authorization to execute them.
`capture` creates a To do or Procrastinated card and leaves activity idle. Only
`begin` grants supported work tools for that turn, after moving the task to Doing.
`start` alone does not register the current turn with the hook gate. For a task
already on another computer, use `attach TASK_UUID --board BOARD_ID --session SESSION`
then `begin`. Session and turn IDs come from the hook context; do not invent them.
A new independent task requires a new request; one turn binds to one task.

Use `update` for metadata, title, body, owner, participants, deadline, or priority.
Replacing `--body` updates only human notes and preserves managed metadata. Use
`finish --state Waiting --next-action "Approve database access" --actor "Alex"`
when another action blocks progress. `complete --accepted` is the separate explicit
acceptance operation. `delete TASK_UUID --confirm TASK_UUID` is destructive and must
be specifically requested. Deletions are never replayed automatically.

Use `links`, `open-task`, and `open-chat SESSION` to inspect links. Opening requires
`--launch`. Native chat URLs are local to their owning computer; no chat history is
synced by this integration. Doska v0.29 strips `codex:` links from Markdown, so the
helper/copyable URI is the fallback; clickable back-navigation needs an upstream
Doska compatibility change. No chats are published automatically.

## Availability decision

The synchronous UserPromptSubmit hook probes the configured backend before letting
Codex work. If it fails, the prompt is blocked and a ten-minute challenge is shown.
The USER can retry or resubmit the identical request with one extra first line:

```text
[doska:offline-once CHALLENGE]
```

or `[doska:untracked-once CHALLENGE]`. Offline queues tracking locally; untracked
stores no task content for later replay. The nonce is bound to this session and
request hash. Do not suggest approval happened because time elapsed. For an actual
continuation of an approved offline task, the user prefixes the prompt with
`[doska:task TASK_UUID]`; an unrelated task must get its own decision.

When offline, use the exact task UUID supplied by the gate in capture and begin.
If no workspace/profile was configured, queued entries require explicit destination
selection before replay; never upload them to a newly selected server silently.
New semantic work in the same chat must not inherit the previous task's choice.

A failed checkpoint during a task denies the next supported work-tool call. Pause,
explain the failure and get a new preflight choice. Already-running commands cannot
be rolled back. Stop/Interrupt update local activity; missing outcomes get at most
one continuation request, then needs-attention rather than an infinite loop.

## Enforcement boundary

Supported command hooks must be installed, trusted, enabled and exercised in the
actual client. Hosted tools and specialized paths can bypass tool hooks. Test
UserPromptSubmit blocking and nested Bash execution in code mode on every target
client before relying on strict gating. This is a workflow guard, not a sandbox or
proof of universal tool interception. No transcript parsing is used.
