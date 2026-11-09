# Recovery and briefs

Every queued event records its original workspace, backend mode and endpoint (never the token), stable task UUID, event UUID, and available task metadata/column baseline. The outbox and local bookkeeping stay private to each computer; do not sync the SQLite directory. Shared board/card markers let another computer rediscover the project and explicitly attach a task.

Use the bridge with the intended `--home` on each computer:

```sh
python3 <skill>/scripts/doska_flow.py replay
python3 <skill>/scripts/doska_flow.py replay --apply
```

The first command is a local-only inspection. Applying requires an available matching backend and is always explicit. No reconnect hook replays events. Different workspace/endpoint, changed managed metadata or column, missing baseline, or deleted card stops recovery. Human notes outside managed metadata remain preserved. Review blocked events and the current card before deciding how to record the outcome manually; there is no force overwrite or automatic rebase. Concurrent writes from different computers still have a race because Doska offers no atomic revision check.

New captures use a stable UUID and search for their marker after an ambiguous timeout. Changes carry event IDs to avoid repeating a confirmed remote update. An ambiguous acknowledgement can require inspection before dependent events; recovery prefers stopping over guessing. Deletion and Done acceptance are never replayed automatically.

Without a configured/identifiable backend, consented offline captures are unassigned. After configuring the intended profile, explicitly bind that new task, confirming its UUID, then inspect and apply:

```sh
python3 <skill>/scripts/doska_flow.py bind TASK_UUID --confirm TASK_UUID --project STABLE_PROJECT_KEY
```

Already assigned events cannot be retargeted. Restore their original profile. A local loopback endpoint identifies a backend on this computer; the bridge cannot prove a reinstalled local database at the same endpoint is the same store. Workspace naming and explicit profile setup remain the user's responsibility. Healthy local access does not establish synchronization with another computer.

```sh
python3 <skill>/scripts/doska_flow.py brief --format markdown
python3 <skill>/scripts/doska_flow.py brief --format json --today 2026-11-09
```

Briefs read all recognized project boards in the configured workspace, use actual columns, and show review requests, waiting actions, due dates, postponed reconsideration dates, old shared activity updates, pending outbox count and up to three suggested priorities. Fresh matching local session activity suppresses old shared-update warnings. Remote activity remains unverified; an old update does not prove an agent failed. Local-only stores show board/card IDs, hosted profiles also provide web links. JSON includes chat references. V1 installs no recurring automation or scheduler.

Preflight availability runs doctor in a child process with a three-second total budget, below the ten-second hook timeout. Failure blocks the supported hook flow and offers the explicit, expiring one-task offline/untracked choice. Unsupported clients or disabled hooks cannot provide this guarantee; follow the conformance checklist before relying on the gate.
