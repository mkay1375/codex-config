# Runtime and local data

Use Python 3.10+ and a free loopback port. The browser and review storage work without Codex or network access; discussions and draft generation additionally require `codex` on PATH, `codex login`, and normal service access. These requests consume the signed-in account's usage. User configuration/MCP integrations are disabled; requests use an ephemeral read-only CLI invocation and instruct it not to use tools or inspect source. Answers are report-grounded, not a new source audit.

The server requires Host/Origin checks and a session token for writes, escapes report HTML, and serves a fixed asset allowlist. It has no multi-user authentication: keep it on localhost. No external assets or analytics are loaded.

Data belongs to the reports folder, not the installed skill. Back up the SQLite database and selected Markdown together before a requested migration. To migrate an existing installation, reuse its database via `--data-dir`; keep the reports root and selected output unchanged. Do not start two servers against the same database/output. Reload the browser after a restart because the write token changes; preserve unsaved editor text first.

An existing selected file remains authoritative. Approvals update only their own sections; manual edits and file-clearing survive restart. Do not delete the database to troubleshoot: it holds discussions, drafts, severity choices and processed flags.
