# Changelog

Newest on top

## 0.1.4

- Added a `purge()` method, which is just `remove()` without any queries.  
- Made empty queries be handled as everything (i.e., `WHERE 1 = 1`) to better match direct SQL queries without a "WHERE" clause.  
    - Enables updating all rows with `patch()` and no query.  
- *Internal*:   
    - Combined and renamed two private methods that are always called together.  
    - Cleaned up docstrings.

## 0.1.3 (2025-01-05)

- WAL mode is now optional but on by default. Adds a wal_checkpoint() method and and calls it by default on close.

**1.0 release candidate**

## 0.1.2 (2025-01-05)

- Adds `patch()` based on SQLite's `JSON_PATCH` ([docs](https://www.sqlite.org/json1.html#jpatch)) to update entries quickly and efficiently without loading into Python.
- Improved documentation internally including more docstrings (and more consistent)
- Fixed missing CLI entry-point in `setup.py`

## 0.1.1 (2024-12-27)

Mostly documentation. Also fixed and clarified using queries on non-dict items.

## 0.1.0 (2024-12-26)

Initial Release