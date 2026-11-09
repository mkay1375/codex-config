# Machine configuration contract

Python 3.11+ is required. `CODEX_HOME` defaults to the user's `.codex` directory.
`doska.local.toml` and `doska-state/` are local and must remain ignored by Git.
The integration is not active merely because its skill files exist.

Local profile (explicitly name a workspace; use a different name for independent,
unsynced stores):

```toml
mode = "local"
workspace = "personal-mac-local"
sync_verified = false
```

Remote profile (Doska desktop is unnecessary):

```toml
mode = "remote"
workspace = "personal-shared"
endpoint = "https://doska.example.com/mcp"
web_url = "https://doska.example.com"
token_env = "DOSKA_ACCESS_TOKEN"
```

The remote token must be provisioned independently using the server's supported
OAuth flow. This bridge does not perform OAuth login or refresh. Expired tokens
cause preflight failure. Never put a token in TOML or a repository file. A
`token_file` is supported for a private, independently maintained token file.
For local mode, the platform's Doska `local-mcp.json` is read on demand unless
`settings_file` explicitly selects another location. The token is never printed.
An endpoint override does not cause fallback to a different store.

`sync_verified` is a user assertion, not a network synchronization test. Local
MCP availability cannot prove cross-device synchronization.
