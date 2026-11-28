# Supported report format

Put one current report per project in the chosen root, named `PROJECT-audit-report-YYYY-MM-DD.md`. When several exist for a project, the lexically newest filename wins. IDs are unique across reports, uppercase letters/digits/hyphens followed by a numeric suffix.

Use this five-column table (replace the example with real findings):

```markdown
| ID | Severity | Area | Finding | Evidence anchor |
|---|---|---|---|---|
| [DEMO-01](#demo-01) | High | Reliability | A concrete current issue | [src/example.py:12](demo/src/example.py:12) |

<a id="demo-01"></a>

### DEMO-01 — A concrete current issue

Describe the evidence, conditions, impact and proposed fix.
```

Evidence links can be absolute or relative to the reports root, but must resolve inside that root. Severity is exactly Critical, High, Medium or Low. Each row needs a matching explicit anchor and `### ID — Title` detail heading. A top-level `##` section after the final finding ends that detail. Unsupported rows or duplicate IDs fail with an error; do not silently omit findings.

Reports are read at server startup. Restart to pick up changes; drafts retain fingerprints so changed source findings are flagged for fresh review. Keep selected-file heading conventions when editing: `## project`, `### severity`, `#### ID`. Older `### ID` selected sections migrate without rewriting their bodies.
