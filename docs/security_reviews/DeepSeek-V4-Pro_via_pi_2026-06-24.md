# JSONLiteDB v0.5.2 — Red-Team Security Report

**Date:** 2026-06-24
**Harness:** [pi](https://github.com/earendil-works/pi-coding-agent) — terminal-based coding agent
**Model:** DeepSeek v4 Pro
**Scope:** Full codebase review (`jsonlitedb/jsonlitedb.py`, `jsonlitedb/cli.py`, `jsonlitedb/__init__.py`, tests)
**Methodology:** Manual static analysis — no automated fuzzing, SAST tools, or dynamic testing was used. Every SQL generation path, file I/O operation, CLI argument handler, and context manager boundary was traced by reading the source. All data-value paths were verified to use parameterized queries; all identifier paths were verified to use either regex validation or SQLite-native quoting.

---

## Executive Summary

JSONLiteDB is a well-written, security-conscious library. The core design — using parameterized queries for all data values, regex-validating identifiers, and escaping paths through SQLite's own quoting mechanism — eliminates the most common class of SQL injection vulnerabilities. The opt-in REGEXP support is properly gated, and the CLI correctly validates table names against an allowed pattern.

The findings below are predominantly defense-in-depth and robustness improvements. The highest-priority item (H1) concerns a state-consistency gap in REGEXP registration. The remaining findings are medium/low severity and address crash risks, DoS vectors, and documentation gaps.

---

## Findings Summary

| Priority | ID  | Issue                                                       | Impact                  |
|----------|-----|-------------------------------------------------------------|-------------------------|
| 🟠 HIGH  | H1  | REGEXP function registration / guard split across call sites | Crash, logic confusion  |
| 🟡 MED   | H2  | `sqlite_quote` trace-callback hack fragile across versions   | Crash / malfunction     |
| 🟡 MED   | M1  | LIKE/GLOB full-table-scan DoS via attacker-controlled pattern | DoS                     |
| 🟡 MED   | M2  | `load_jsonl` / `import_jsonl` no size/depth limits            | DoS (memory/CPU)        |
| 🟡 MED   | M3  | `Query._from_equality` uses `_key = True` sentinel hack       | Crash risk              |
| 🟡 MED   | M4  | `parse_index_expressions` fragile custom SQL parser           | Wrong output            |
| 🟡 MED   | M5  | `backup(reopen=True)` REGEXP state inconsistency              | Crash                   |
| 🟢 LOW   | L1  | Path traversal possible in all file operations                | Information disclosure  |
| 🟢 LOW   | L2  | `__del__ = close` — nondeterministic cleanup                  | Data loss               |
| 🟢 LOW   | L3  | Unescaped double quotes in JSON path keys                     | DoS (SQL error)         |
| 🟢 LOW   | L4  | `Row.get` bare `except Exception` masks errors                | Error masking           |
| 🟢 LOW   | L5  | Env vars read only at import time; docs imply runtime effect  | User confusion          |

---

## Recommendations

### H1 — Unify REGEXP registration and guard logic (HIGH)

The `_configure_connection` method registers the `REGEXP` function based on `regex_enabled()` at **connection-open time**, while `Query._compare` checks `regex_enabled()` at **query-build time**. These can diverge if the module-level `ENABLE_REGEX`/`DISABLE_REGEX` flags change between connection creation and query execution.

**Scenario A:** REGEXP was disabled at connection time (no function registered), then enabled before query. `_compare` emits `REGEXP` in the SQL, but SQLite has no registered function → `OperationalError: no such function: REGEXP`. An attacker who can influence the toggle timing can crash the process.

**Scenario B:** REGEXP was enabled at connection time (function registered), then disabled. `_compare` correctly blocks the query with `RegexDisabledError`. However, the function **remains registered** on the connection and could theoretically be reached via paths that bypass `_compare`, such as `_render_path_sql()` used for ordering.

**Recommendation:** Store the registration decision on the `JSONLiteDB` instance (e.g., `self._regex_allowed = regex_enabled()` at `__init__` time) and check that attribute in `_compare` rather than re-reading the module-level globals. This makes each connection's behavior consistent for its entire lifetime. Alternatively, register the REGEXP function lazily at first use rather than at connection-open time.

### H2 — Replace `sqlite_quote` with a stable quoting mechanism (MEDIUM, downgraded from HIGH)

The `sqlite_quote` function creates a temporary `:memory:` database, runs `SELECT ?`, captures the trace callback output, and extracts the literal:

```python
quoted = "\n".join(quoted.getvalue().splitlines()[1:])
```

This depends on undocumented formatting of `sqlite3`'s C-level trace output. If Python's `sqlite3` module or the underlying SQLite library changes how `sqlite3_trace_v2` formats statements (e.g., adds a prefix line, changes whitespace, or removes the leading `SELECT` line break), the extracted literal could be truncated or corrupted.

**Realistic impact:** Because `sqlite_quote` output is always embedded into a SQL string-literal context (e.g., `JSON_EXTRACT(data, <result>)`, `DROP INDEX IF EXISTS <result>`), a corrupted extraction would produce a **syntax error or wrong path**, not SQL injection. The trace output is always a properly quoted SQL literal from SQLite itself; even if the first-line stripping logic misbehaves, the remnant would be something like `"'hello'"` or `""` — never a closed string followed by free-form SQL. No viable injection gadget was identified. The risk is limited to crashes, incorrect query results, or failed index operations.

**Recommendation:** Replace with one of:

1. `SELECT QUOTE(?)` on the main connection and parse the return value.
2. Use an in-memory DB + `SELECT QUOTE(?)` → fetch the result directly instead of trace parsing.
3. If performance is critical, implement SQLite string escaping manually according to the well-documented SQLite quoting rules (single-quote doubling).

This eliminates dependence on undocumented trace output format and future-proofs the code.

### M1 — Document and guard against LIKE/GLOB full-table-scan DoS

LIKE patterns starting with `%` or `_` and GLOB patterns starting with `*` or `?` force full table scans because indexes cannot be used. An attacker who controls pattern input can cause repeated expensive queries.

**Recommendation:** Document this clearly in the query API docs. Consider adding a configurable row-limit or query-timeout guardrail.

### M2 — Add size/depth limits to `load_jsonl` / `import_jsonl`

No limits are enforced on file size, JSON nesting depth, or number of lines in JSONL. An attacker who controls a file path can cause out-of-memory or CPU exhaustion.

**Recommendation:** Add configurable limits (`max_size`, `max_depth`, `max_lines`). Consider using `ijson` or similar streaming parser for `.json` files.

### M3 — Replace `_key = True` sentinel with a dedicated object

`Query._from_equality` sets `self._key = True` with the comment `# To fool it`. If any future code path iterates over `_key` without the `isinstance(list)` guard, it will crash on a `bool`. `_clone()` currently handles it correctly, but this is fragile.

**Recommendation:** Replace with `_KEY_FROM_EQUALITY = object()` and check `self._key is _KEY_FROM_EQUALITY` where needed.

### M4 — Harden or replace `parse_index_expressions`

The custom tokenizer in `parse_index_expressions` parses `CREATE INDEX` DDL from `sqlite_schema.sql`. It tracks quote state, parenthesis depth, and commas to split index expressions. This is inherently fragile against future SQLite output format changes.

**Recommendation:** Prefer `PRAGMA index_list` + `PRAGMA index_info` + `PRAGMA index_xinfo` for introspection. If DDL parsing is still needed, add comprehensive tests against exotic index definitions. At minimum, validate the parser output against the expected number of indexed columns.

### M5 — Fix `backup(reopen=True)` REGEXP state

Same root cause as H1. When `backup(reopen=True)` is called, `_configure_connection` reads the current module-level `regex_enabled()` value, which may differ from the original connection's state.

**Recommendation:** As with H1, store the REGEXP decision on the instance and re-apply it during reopen.

### L1 — Document path traversal risk

All file operations (`dbpath`, `load_jsonl`, `export_jsonl`, `backup`) accept arbitrary paths. A wrapper that passes user input directly to these methods could allow reading or writing to unintended files.

**Recommendation:** Document that callers must sanitize paths. Consider offering a configuration option to restrict file operations to a base directory.

### L2 — Recommend explicit close or context manager

`__del__ = close` is unreliable because Python `__del__` is not guaranteed to run. WAL/SHM sidecar files or uncommitted writes could be lost.

**Recommendation:** Add `__enter__`/`__exit__` at the `JSONLiteDB` class level to support `with JSONLiteDB(...) as db:`. Document that explicit `.close()` is preferred.

### L3 — Validate key names for JSON-path-disallowed characters

`_query_tuple2jsonpath` wraps string keys in double quotes without escaping embedded `"`. A key like `a"b` produces the invalid path `$."a"b"`, causing a SQLite error at runtime.

**Recommendation:** Either escape or reject keys containing `"`, `[`, `]`, `.` early with a clear error message. The README already warns about this limitation.

### L4 — Narrow `Row.get` exception handler

```python
def get(self, key, default=None):
    try:
        return self[key]
    except Exception:
        return default
```

A bare `except Exception` catches and suppresses everything, including `KeyboardInterrupt` and `MemoryError`.

**Recommendation:** Change to `except (IndexError, KeyError)`.

### L5 — Clarify environment variable timing in documentation

`_env_to_bool` reads environment variables at module import time. Setting `JSONLITEDB_ENABLE_REGEX` after import has no effect. The documentation correctly explains the code-level `jsonlitedb.ENABLE_REGEX = True` approach but may mislead users into thinking `os.environ` changes at runtime will be picked up.

**Recommendation:** Add a note: "Environment variables must be set before importing `jsonlitedb`."

---

## Detailed Analysis

### Methodology

The following surface areas were examined:

- **SQL injection vectors**: All SQL generation paths, including table names, paths, function names, literal values, and the `sqlite_quote` helper.
- **Query building**: `Query` class, `_query2sql`, `_from_equality`, `_compare`, `_logic`, `wrap_`, `lower_`, `length_`, path tuple normalization, `_orderby2sql`.
- **File I/O**: `load_jsonl`, `export_jsonl`, `backup`, `read_only`, `create`, and constructor path handling.
- **Context management**: `__enter__`/`__exit__` with nested counter, transaction semantics, `__del__`.
- **CLI surface**: Argument parsing, `parse_known_args` extras handling, JSON filter parsing, file/stderr output.
- **Configuration**: `ENABLE_REGEX`, `DISABLE_REGEX`, `DISABLE_METADATA`, `SQL_DEBUG`, `JSONLITEDB_CLI_TABLE` env vars.
- **Error handling**: Exception classes, try/except shapes, error message leaks.
- **Data integrity**: Update/insert/patch/delete paths, unique index enforcement, `duplicates` handling.

### What Was Verified as Safe

The following areas were scrutinized and confirmed to be secure:

#### SQL Injection — Data Values

All user-supplied values go through parameterized queries using `?` or named `:jldb_*` placeholders:

- `insert` / `insertmany`: Values pass through `json.dumps()` then `JSON(?)` parameter.
- `_dump=False` path: Raw strings pass through `JSON(?)` parameter (SQLite validates JSON syntax).
- `query` / `render_query`: Comparison values use randomly generated named parameters (`randkey()`).
- `patch`: Patch document uses `JSON(:patchitem)` parameter.
- `remove` / `delete_by_rowid`: Values use `?` parameters.
- `execute` / `executemany`: Caller-supplied SQL; no injection in the wrapper itself.

#### SQL Injection — Table Names

`_validate_table_name` enforces `^[A-Za-z_][A-Za-z0-9_]*$`. All table name interpolation uses this validated value. Injection impossible.

#### SQL Injection — `wrap_()` Function Names

`wrap_()` validates function names against the same `^[A-Za-z_][A-Za-z0-9_]*$` regex. This prevents injection while still allowing any SQLite built-in scalar function. Unknown function names cause `sqlite3.OperationalError` at execution time, which is safe.

#### SQL Injection — Aggregate Functions

`aggregate()` validates function names against a hardcoded set: `{"AVG", "COUNT", "MAX", "MIN", "SUM", "TOTAL"}`. Injection impossible.

#### SQL Injection — WAL Checkpoint Modes

`wal_checkpoint()` validates `mode` against `{None, "PASSIVE", "FULL", "RESTART", "TRUNCATE"}`. Injection impossible.

#### SQL Injection — `drop_index_by_name`

Uses `sqlite_quote(name)` to escape the index name before interpolation into `DROP INDEX`. Safe.

#### SQL Injection — Index Names

Index names are MD5 hashes of path signatures plus optional `_UNIQUE` suffix. They never contain user-controlled text beyond what the hash produces. Safe.

#### CLI Input Handling

- Table name from `--table` or `JSONLITEDB_CLI_TABLE` env var is validated by `_validate_table_name` before use.
- JSON filter values from `--json` and positional args are parsed by `json.loads`, not `eval`.
- `parse_cli_filter_value` uses `json.loads` with fallback to raw string; the string is later parameterized.
- CLI `patch` document goes through `json.loads` before passing to `db.patch()`.
- CLI `delete` requires either filters or `--allow-empty` flag; no accidental full-table deletion.
- File input modes (`.json` vs `.jsonl`) are determined by extension, not content-type sniffing.
- `parse_known_args` extras are properly folded into positional inputs or rejected with an error.

#### REGEXP Disabled by Default

`ENABLE_REGEX` defaults to `False`. The `@` operator raises `RegexDisabledError` before any SQL is generated. The `DISABLE_REGEX` flag is a hard override that wins over any `ENABLE_REGEX` setting. This is a well-designed defense-in-depth pattern.

#### Metadata Table Initialization

The `_init` method catches `sqlite3.OperationalError` and only initializes a new schema when the error message contains `"no such table"`. Other operational errors (e.g., `"database is locked"`) propagate correctly. The `DISABLE_METADATA` env var allows metadata-free operation.

#### Backup Integrity

The `backup` method uses SQLite's native backup API (`sqlite3.Connection.backup`), which is atomic and consistent. The `reopen` path closes the old connection only after the backup completes.

#### Context Manager Nesting

The `__enter__`/`__exit__` counter correctly batches multiple nested `with db:` blocks into a single SQLite transaction. Inner exceptions propagate correctly; the outer `__exit__` either commits or rolls back based on whether the exception was caught.

#### Order-By Injection

`_orderby2sql` normalizes all inputs through `build_orderby_pairs`, which produces typed tuples `(path_or_field, order, kind)`. The `order` is always `"ASC"` or `"DESC"` (set by the function, never from user input). Paths go through `sqlite_quote`. No injection possible.

#### JSON Path Handling

`_query_tuple2jsonpath` normalizes all path formats into properly-quoted JSON paths. Integer indices use `[%d]` formatting. String keys use `"key"` wrapping. All paths ultimately go through `sqlite_quote` before embedding in SQL. Safe aside from the unescaped-double-quote issue (L3).

### Borderline / Risk-Acceptance Items

Several design decisions carry inherent risk but are unlikely to be changed:

1. **`execute`/`executemany` are public**: These expose raw SQL execution. They are documented as escape hatches and are necessary for a SQLite wrapper. Callers are responsible for their own SQL safety.

2. **`_dump=False` bypasses `json.dumps`**: Designed for zero-overhead JSONL insertion. SQLite's `JSON()` function validates the input. If `JSON()` is ever relaxed, malformed data could be stored. This is a SQLite-level concern.

3. **JSON Merge Patch null semantics**: `patch()` cannot set a value to JSON `null` because `None` means "remove the key" per RFC 7396. This is documented behavior, not a bug.

4. **No transaction isolation control**: All operations share the default SQLite isolation level. Concurrent writers will see `SQLITE_BUSY`. This is acceptable for a single-writer embedded database.

5. **No built-in encryption**: Database files are plain SQLite. Callers must use SQLite encryption extensions or filesystem encryption if needed.

### Areas Not Tested

The following were not exhaustively tested but are noted for awareness:

- **Concurrent access patterns**: Multiple readers, single writer, WAL mode checkpoint behavior under load.
- **Large-scale performance**: Behavior with millions of rows, deeply nested JSON, very wide documents.
- **Fuzzing**: No fuzzing was performed on path parsing, query building, or CLI argument handling.
- **Dependency supply chain**: Only standard library and `setuptools`/`wheel` build dependencies. No runtime dependencies beyond stdlib.
- **PyPy compatibility**: A known incompatibility with `sqlite3.Row` is documented and handled in tests.

---

## Conclusion

JSONLiteDB v0.5.2 demonstrates strong security fundamentals. The HIGH finding (H1) represents a real state-consistency issue with limited exploitability today. The MEDIUM findings are defense-in-depth improvements addressing fragility, DoS vectors, and code hygiene. Addressing H1 along with the MEDIUM items would bring the library to an excellent security posture. No CRITICAL or HIGH-impact injection vulnerabilities were identified.

The author's approach — parameterized queries everywhere, regex-validated identifiers, opt-in dangerous features, and a clearly documented attack surface — is commendable and should serve as a model for similar embedded database wrappers.