# Security Review: JSONLiteDB

Date: 2026-04-15

Reviewer: OpenAI Codex (GPT-5-based coding agent) operating in the local repository workspace at the user's direction.

Review type: targeted manual application security review with remediation follow-up. This was not an independent third-party audit, not a formal penetration test, and not a source/binary review of SQLite itself or Python runtime internals.

Scope: `jsonlitedb/`, CLI, and local maintenance scripts in this repository.

Method: manual code review, targeted runtime checks, and test execution (`python -m pytest tests/test_jsonlitedb.py tests/test_cli.py`).

## Assessment Context

This review was performed after a request for a thorough security and vulnerability scan of the repository. The review started as a findings report, then was updated after code changes were made during the same review cycle to address some identified issues. This document reflects the repository state after those remediations.

Primary focus areas:

- SQL construction and SQL injection resistance
- Query-surface safety, especially regex handling
- CLI argument handling and file/path handling
- Dangerous local execution surfaces in project maintenance scripts
- Abuse-resistance issues such as unbounded input or output handling

Out of scope or only partially covered:

- Vulnerabilities inside CPython, `sqlite3`, SQLite JSON1, Jupyter, or nbconvert themselves
- OS-level hardening, filesystem permissions, containerization, or deployment-specific controls
- Dependency supply-chain review beyond directly observable repository behavior
- Fuzzing, long-duration load testing, or adversarial performance benchmarking

## Review Process

The review process was:

1. Enumerate repository files and identify attack-relevant surfaces in the library, CLI, tests, and maintenance scripts.
2. Inspect SQL construction paths, query composition, filesystem access, subprocess usage, and environment-variable-controlled behavior.
3. Run targeted runtime checks for suspected edge cases, especially around regex behavior, URI handling, and identifier handling.
4. Execute the focused test suite to validate findings and confirm behavior.
5. Implement selected remediations requested during the review cycle.
6. Re-run tests and update this report so the final document reflects current behavior rather than only the pre-remediation state.

## Evidence Base

This report is based on:

- Direct source review of `jsonlitedb/jsonlitedb.py`, `jsonlitedb/cli.py`, `build_help.py`, `copy_to_github.py`, and the associated tests
- Targeted local runtime checks in the repository workspace
- Focused test execution via `python -m pytest tests/test_jsonlitedb.py tests/test_cli.py`

## Executive Summary

I did not find a straightforward remote code execution path, shell injection path, or obvious SQL injection in the public JSONLiteDB query helpers. Most query values are bound parameters, and JSON paths used in SQL expressions are passed through `sqlite_quote(...)` before interpolation.

The main security concerns are:

1. The documentation/publish toolchain executes notebooks from the repository and therefore runs arbitrary code from repo content.
2. Remaining lower-severity concerns are a fragile read-only URI construction path and generally unbounded input processing.

Update after remediation:

- Table-name handling has been hardened since the initial review. JSONLiteDB now rejects invalid table names instead of silently rewriting them, which removes the collision/empty-name issue that was previously called out here.
- `REGEXP` is now opt-in via `JSONLITEDB_ENABLE_REGEX=1` or `jsonlitedb.ENABLE_REGEX = True`, and disabled mode raises in JSONLiteDB before SQL execution. This removes the prior concern that disablement depended on the SQLite build.

Test note: after the remediation updates in this review cycle, the focused test suite passes.

## Prioritized Findings

### 1. Medium: repository maintenance scripts execute arbitrary notebook code

Affected code:

- `build_help.py:29-45`
- `copy_to_github.py:22-25`

Why this matters:

- `build_help.py` opens tracked notebooks and executes them with `ExecutePreprocessor`.
- `copy_to_github.py` automatically runs `build_help.py` before syncing/publishing.

Impact:

- Any malicious or compromised notebook committed to the repo can run arbitrary code on the maintainer machine when these scripts are run.
- This is a supply-chain / maintainer-workstation risk rather than a package-consumer runtime risk.

Attack scenario:

- A malicious notebook is introduced in a branch or commit.
- A maintainer runs `copy_to_github.py`.
- The notebook executes with the maintainer's local permissions before publication.

Recommendation:

- Restrict execution to an explicit allowlist of notebooks instead of `git ls-files *.ipynb`.
- Run notebook execution in an isolated environment or disposable container.
- Require an explicit flag before executing notebooks during publish/sync.
- Document clearly that these scripts execute repository code and must not be run on untrusted branches.

### 2. Low: `read_only()` builds SQLite URI strings by concatenation

Affected code:

- `jsonlitedb/jsonlitedb.py:169-170`

Why this matters:

- `read_only()` constructs `file:{dbpath}?mode=ro` by raw string concatenation.
- Paths containing URI metacharacters such as `?` or `#` are parsed inconsistently.

Observed during review:

- `JSONLiteDB.read_only("safe.db?mode=ro")` produced `OperationalError: no such access mode: ro?mode=ro`
- `JSONLiteDB.read_only("x?mode=ro&cache=shared")` produced `OperationalError: no such cache mode: shared?mode=ro`

Impact:

- This is primarily a robustness and semantic-integrity issue.
- In higher-level wrappers, attacker-controlled path strings could cause unexpected open failures or option confusion.

Recommendation:

- Properly encode the path portion before constructing the SQLite file URI.
- Alternatively, reject `dbpath` values containing URI metacharacters in `read_only()`.
- Add tests covering `?`, `#`, spaces, and other URI-sensitive characters.

### 3. Low: several CLI/library operations are unbounded and can be abused for memory or disk exhaustion

Affected code:

- `jsonlitedb/jsonlitedb.py:245-276`
- `jsonlitedb/jsonlitedb.py:315-358`
- `jsonlitedb/cli.py:659-706`

Why this matters:

- `insertmany()` materializes `items = listify(items)`.
- `.json` input paths are fully loaded with `json.load(...)`.
- Query/dump helpers can emit arbitrarily large outputs.

Impact:

- A service that exposes JSONLiteDB operations directly to untrusted clients can be forced into high memory use, large disk growth, or expensive scans.
- This is common abuse-resistance work rather than a library-specific exploit.

Recommendation:

- Document that CLI imports are trusted/local tooling, not hardened ingestion endpoints.
- For server-side use, add external limits on input size, row count, and output volume.
- Consider streaming JSON-array ingestion for very large files if this library is expected to handle untrusted bulk input.

## Positive Security Properties

- I did not find a direct SQL injection in query helpers. Query values are bound parameters, and JSON path fragments are SQLite-quoted before interpolation.
- CLI subprocess usage in this repo uses argument lists rather than shell strings; I did not find `shell=True`.
- `create()` correctly rejects `uri=True`, which avoids a class of SQLite URI confusion when callers expect plain file creation.
- CLI `delete` refuses an empty filter set unless `--allow-empty` is provided.
- Table names are now validated against `^[A-Za-z_][A-Za-z0-9_]*$` and rejected on invalid input, avoiding the prior identifier-collision behavior.
- `REGEXP` is now disabled by default and must be explicitly enabled. Disabled mode is enforced by JSONLiteDB query construction, not by SQLite implementation details.

## Residual Risks and Test Gaps

- The library intentionally exposes `execute()` and `executemany()`. Any application that passes untrusted SQL into those methods bypasses the library's safer query helpers.
- There are not enough security-focused tests around:
  - `read_only()` URI escaping
  - oversized input behavior

## Limitations

- This review was code-centric and behavior-centric; it did not include external network probing, package ecosystem scanning, or dynamic analysis outside the local development environment.
- Severity ratings here are relative to the likely ways this repository is used. If JSONLiteDB is embedded inside a network-facing multitenant service, abuse-resistance concerns may merit higher priority.
- Maintenance-script findings apply primarily to maintainers and contributors running repository tooling locally, not to downstream consumers importing the library at runtime.

## Recommended Remediation Order

1. Isolate or gate notebook execution in the maintenance workflow.
2. Harden `read_only()` URI construction.
3. Add abuse-resistance tests and documentation for untrusted input scenarios.
