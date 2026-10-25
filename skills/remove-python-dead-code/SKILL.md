---
name: remove-python-dead-code
description: Find or remove dead Python code, including unused dependency injection, reexport-only APIs, and orphaned call chains. Use for Python dead-code audits and cleanup; distinguish runtime use, test-only utilities, framework hooks, and retained schema definitions.
---

# Remove Python Dead Code

Find code with no supported execution path and, when cleanup is requested, remove the whole
unused chain while preserving active behavior and the user's exceptions. An audit request
is read-only. Follow the repository's instructions and any requested worktree or PR workflow;
this skill does not independently authorize publishing, merging, or schema changes.

## Establish what runs

Inspect project configuration, entry points, scripts, tests, and framework registration.
Identify the supported Python version and use a compatible parser. Include CLI commands,
workers, scheduled jobs, migrations, plugins, and dynamically loaded modules as roots where
applicable. Search tracked tooling and documentation as well as application source.

Use `rg` for references and AST analysis or existing static-analysis tools to generate
candidates. Coverage and tools such as Vulture provide leads, not proof of dead code. Report
parse failures or excluded directories instead of silently treating them as scanned.

## Trace execution, not just references

For each candidate, follow its callers back to a supported root. Inspect how a dependency is
consumed, not merely whether its name appears. Specifically check:

- **Discarded injection:** a factory is imported and passed through constructors, but its final
  recipient never stores or invokes it. Trace the factory, implementation, request/result
  types, configuration role, and test fake as one candidate chain.
- **Exports without consumers:** imports in `__init__.py`, `__all__`, type annotations, and
  documentation do not establish runtime use. Check downstream consumers before removing a
  public API; a published library may support external callers absent from the repository.
- **Dead callers:** a helper called only by an unused wrapper is also a candidate. Recompute
  callers after each removal to find newly orphaned functions, constants, and imports.
- **Disabled paths:** constant-false guards, always-raising implementations, and tool preparation
  that always hides an operation may leave inert features behind. Distinguish intentional
  compatibility or planned functionality from removable leftovers. Preserve explicit user
  exclusions without activating or rewriting them.
- **Test-only implementations:** a backend exercised by tests may never be selected by production
  factories. Verify the selected implementation. Keep intentional diagnostic APIs, fixtures,
  teardown helpers, and documented extension points unless their removal is in scope.
- **Ignored arguments and state:** check constructor parameters, stored attributes, and forwarded
  arguments. An ignored parameter can be removed without the surrounding function being dead;
  update positional and keyword callers and preserve any necessary argument-evaluation effects.

Before declaring a candidate unused, rule out implicit consumers:

- Decorators and registration tables; Pydantic validators and serializers; framework callbacks;
  protocol/base-class overrides; magic methods and property access.
- `getattr`, string-based dispatch, import paths in configuration, plugin discovery, CLI and
  package entry points, serialization aliases, and persisted enum/configuration values.
- ORM metadata imports and migrations. Search raw SQL and table/column names as well as Python
  symbols. An ORM class with no ordinary callers can still control schema generation or back
  an actively queried table. Treat schema retirement as a separate change.

Classify findings as **verified unused**, **runtime-unused but intentionally supported/test-only**,
or **uncertain**. Attach a path, line, and concrete caller-chain evidence. Do not claim a full
proof from a repository-wide name count.

## Remove and verify

When removal is authorized, delete verified unused implementations and their exclusive wiring:
exports, dependency parameters, roles/defaults, constants, imports, test fakes, and tests that
exercise only the removed implementation. Retain shared helpers and meaningful tests of active
behavior. Check persisted configuration compatibility before removing names or roles.

Update affected callers and current documentation, including generated indexes when their
source of truth is available. Do not rewrite historical migration files to erase old symbols.
Avoid unrelated refactoring or creating replacement APIs for behavior nobody uses.

Search again for removed symbols and for newly orphaned dependencies. Run the repository's
required formatting, lint, type, dependency, and import-boundary checks plus relevant behavior
tests. Broaden testing when shared infrastructure or entry points changed. Do not run checks
while another process temporarily stashes or rewrites the same working tree.

Classify failures before changing code. A download failure or a test timeout is not evidence
that removal was safe or broken. Retry the affected case when justified; compare with the base
when causality is unclear. Report the original result and retry separately. Do not delete tests
or weaken assertions to make cleanup pass.

Review the complete final diff for broken callers, dynamic hooks, schema changes, lost behavior,
and violated exclusions. Summarize what was removed, what was intentionally retained, the
verification actually performed, and any unresolved uncertainty. Commit or create a PR only
when requested or authorized by the surrounding workflow.
