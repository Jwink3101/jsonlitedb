# Changelog

Newest on top

## 0.4.0 (2026-2-27)

- Add `Query.exists_()` and `Query.missing_()`. These remove the need for `JSONLiteDB.count_by_path_exists` and `JSONLiteDB.count_by_path_exists`. Those are now noted as deprecated in the docs but do not (yet) raise a warning. They may in the future.
- Adds `or_` and `and_`. `(db.Q.a == 1) & (db.Q.b == 2) <==> (db.Q.a == 1).and_(db.Q.b == 2)`
    - Also add `not_` though this breaks the fluent flow. `(~(db.Q.a == 1)) & (db.Q.b == 2) <==> (db.Q.a == 1).not_().and_(db.Q.b == 2)`
    - Complex example:
        - Operator form: `(((db.Q.a == 1) | (db.Q.b == 2)) & (~(db.Q.c == 3))) | ((db.Q.d >= 4) & (db.Q.e < 10))`
        - Fluent form: `(db.Q.a == 1).or_(db.Q.b == 2).and_((db.Q.c == 3).not_()).or_((db.Q.d >= 4).and_(db.Q.e < 10))`
        - SQL: `( ( ( ( JSON_EXTRACT(data, '$."a"') = 1 ) OR ( JSON_EXTRACT(data, '$."b"') = 2 ) ) AND ( NOT ( JSON_EXTRACT(data, '$."c"') = 3 ) ) ) OR ( ( JSON_EXTRACT(data, '$."d"') >= 4 ) AND ( JSON_EXTRACT(data, '$."e"') < 10 ) ) )`
- CLI: Changed the order parsing to be determinstic for adding items. Greatly simplifies the code

## 0.3.2 (2026-02-24)

- Query composition operators are now non-mutating:
    - `&`, `|`, and `~` return new `Query` objects instead of modifying operands
    - unary `+` / `-` order modifiers also return new `Query` objects
- Added regression tests and docstring notes for non-mutating operator behavior
- Fixed CLI positional input handling for `insert` / `import` / `add` when trailing positional inputs are parsed as extras
- Added CLI tests for the positional-extra parsing path and associated error branches

## 0.3.1 (2026-02-15)

- `load_jsonl` (aliased to `import_jsonl`) now also accepts a file object
- Minor documentation & docstrings
- CLI: 
    - `import` is shorthand for `insert --file` and `add` is `insert --json`
    - Divide the commands more clearly into write and read-only

~~This is likely the 1.0 candidate but that may change.~~

## 0.3.0 (2026-02-09)

- Refactor including putting CLI into its own
- Add a lot more to CLI for more control.

Note, much of this was done with the help of ChatGPT and `codex` but all changes were reviewed, modified, and accepted. The refactor and additional CLI was still reviewed but less closely.

## 0.2.0 (2026-02-09)

- Updated the CLI `insert` interface to allow adding a single item as well. Deprecated older interface but is (currently) still working and backwards compatible. 
- Updated the CLI `query` interface to control the output format. Also added --json for query.
- Adds _limit to db.count() to match query() even though it is functionally useless.

Note, much of this was done with the help of ChatGPT and `codex` but all changes were reviewed, modified, and accepted.

## 0.1.12 (2026-02-08)

- Found a *minor* security issue related to filling placeholders. It would cause an inappropriate KeyError but would otherwise be okay. Moved to named SQL parameters and added a test for this pathology.
- Added the ability to disable `REGEXP` / `@` for handling untrusted input that could cause catastrophic backtracking and consume CPU for a long time (ReDoS). Tested
- Better handled errors in `_init`
- (*minor*) Replace `split_no_double_quotes` with a state-machine approach. Removed additional utils around it

Note, much of this was done with the help of ChatGPT and `codex` but all changes were reviewed, modified, and accepted.

## 0.1.11 (2026-01-12)

- Added `import_jsonl()` and `export_jsonl()` helpers to mirror CLI workflows.
- Added `stats()` for quick row/index/page metadata.
- Extended `update()` to accept `*items` and added `update_many()` as a thin wrapper.
- Expanded public exports in `__all__`.

Note, much of this was done with the help of ChatGPT and `codex` but all changes were reviewed, modified, and accepted.

## 0.1.10

- Added query CLI subcommand with filtering, ordering (including nested paths), and limits.
- Added `find_one`, `count_by_path_exists`, and public `explain_query`/`analyze` helpers.
- Improved and standardized docstrings across the module.
- Moved packaging metadata into `pyproject.toml` (PEP 621) and removed `setup.py`.

Note, much of this was done with the help of ChatGPT and `codex` but all changes were reviewed, modified, and accepted.

## 0.1.9

- Adds `_orderby` to `query()`, `query_by_path_exists()`, and related calls. Allows for complex ordering and ascending or descending. 
- Adds `memory()` constructor as a shortcut for `:memory:`
- Adds a couple of aliased commands such as `key_counts()` to `path_counts()` to match `keys()`, etc.
- Cleans up documentation, fixes spelling errors, clarifies behavior of some internal but reusable utilities.

## 0.1.8

- Added `_limit` to query and explained the advantage of `query()` vs `query_one()`
- Changed the `__getitem__` and `__delitem__` to raise an `IndexError` if the rowid does not exist. Improved documentation and updated tests.
- Improved docstrings and documentation.

## 0.1.7

- Added `keys()` method as shortcut for `path_counts(...).keys()`

## 0.1.6

- Updated the CLI to make it more clear how to specify `--table` by making it an option on each as opposed to a global option.

## 0.1.5

- Accept pathlib.Path objects or existing database connections. The latter enabled additional flexibility to backup and make copies
- Adds about() method
- Cleaned up repo

## 0.1.4

- Added a `purge()` method, which is just `remove()` without any queries.  
- Made empty queries be handled as everything (i.e., `WHERE 1 = 1`) to better match direct SQL queries without a "WHERE" clause.  
    - Enables updating all rows with `patch()` and no query.  
- *Internal*:   
    - Combined and renamed two private methods that are always called together.  
    - Cleaned up docstrings.

## 0.1.3 (2025-01-05)

- WAL mode is now optional but on by default. Adds a wal_checkpoint() method and and calls it by default on close.

~~**1.0 release candidate**~~

## 0.1.2 (2025-01-05)

- Adds `patch()` based on SQLite's `JSON_PATCH` ([docs](https://www.sqlite.org/json1.html#jpatch)) to update entries quickly and efficiently without loading into Python.
- Improved documentation internally including more docstrings (and more consistent)
- Fixed missing CLI entry-point in `setup.py`

## 0.1.1 (2024-12-27)

Mostly documentation. Also fixed and clarified using queries on non-dict items.

## 0.1.0 (2024-12-26)

Initial Release
