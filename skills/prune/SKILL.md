---
name: prune
description: Reduce maintained lines of code while preserving supported behavior, performance, and readability. Use for code pruning, shrinking implementations, and removing unnecessary complexity; not for feature removal or syntax compression.
---

# Prune

Reduce maintained code by removing unnecessary complexity. Line reduction is the objective; behavior, performance, and readability are acceptance conditions. A no-change result is valid. Never force a deletion quota.

## Acceptance rules

- Preserve supported features, public interfaces, edge cases, errors, side effects, ordering, and meaningful operational behavior such as logging. Treat compatibility obligations as behavior, including consumers outside the repository.
- Keep reasoning equally clear or clearer for the next maintainer. Prefer explicit control flow and familiar idioms over dense expressions, clever tricks, excessive indirection, or generic abstractions with flags and callbacks.
- Preserve performance, including algorithmic complexity, database and network calls, allocations, memory use, startup cost, and repeated work where relevant. Investigate plausible regressions; unresolved material uncertainty disqualifies a candidate.
- Count all changed production files, including added helpers. Do not claim savings from moving implementation into dependencies, generated files, or other repositories, or from changing formatting, stripping useful comments, or deleting tests.
- Do not add a dependency merely to shorten code. Reuse established functionality already available when its semantics and costs fit.
- Do not weaken tests, assertions, validation, or error handling to make a reduction pass. Remove a check only when its redundancy is demonstrated for all supported paths.

## Find justified reductions

Understand the requested scope and relevant behavior before editing. Establish the starting diff and relevant verification baseline so existing failures and user edits remain distinguishable from pruning changes.

Prioritize:

- Proven dead code and obsolete compatibility branches whose support obligations have ended.
- Redundant state, conversions, wrappers, branches, intermediate objects, and repeated computations.
- Simpler control flow that preserves evaluation order and side effects.
- Custom implementations replaceable by existing project or standard-library functionality with equivalent semantics.
- Duplicated logic that represents the same rule and becomes easier to understand when consolidated.

Similar-looking code can encode different business rules. Do not combine it solely for textual similarity. Keep an abstraction only when the entire change reduces maintained code and makes its callers easy to understand.

Before deleting apparently unused code, inspect callers, configuration, exports, dynamic registration, reflection, framework hooks, serialization, and external entry points as applicable. Absence from a text search alone does not establish that code is unused. Leave uncertain candidates unchanged.

Avoid opportunistic redesign, feature changes, dependency upgrades, and unrelated cleanup. Prefer focused, independently verifiable reductions.

## Verify each retained change

For each candidate, establish why the old and new implementations are equivalent, including relevant failure paths and boundary conditions. Passing existing tests is evidence, not proof of equivalence.

Run checks appropriate to the affected behavior: relevant tests, type checks, lint, or builds. Add targeted behavioral coverage when a meaningful uncertainty warrants it; do not create tests that merely mirror implementation details. Preserve useful existing tests even when the test suite grows.

Inspect performance implications explicitly. When a change can affect runtime or resource use, compare representative before-and-after measurements under comparable conditions using the project's existing tooling when available. Interpret results against measurement noise. Do not invent a universal allowed regression percentage or treat fewer lines as evidence of faster execution. If required performance evidence cannot be obtained, leave that candidate unchanged.

Review the complete diff for behavior changes, readability, hidden code movement, and costs introduced at callers. Revert or revise candidates that fail an acceptance condition. If validation cannot establish the required confidence, do not present the change as verified or retain it merely to reach a reduction target.

## Measure and report

Use the same counting method before and after, with normal project formatting preserved. Report production lines added, removed, and net removed across all affected production files. Report test and supporting-file changes separately; disclose total maintained-line impact when those changes offset production savings. Exclude generated and vendored code from claimed savings. Explain any limitation in the counting method.

Finish concisely with:

- Net code reduction and what became simpler.
- Verification performed, including performance evidence when relevant.
- Material limitations and worthwhile candidates left unchanged, if any.

Stop when no further justified reductions remain within scope. Do not promise exhaustive minimality or absolute behavioral equivalence beyond the evidence available.
