<!-- md-demo
setup: |
  import init_demo_mode
-->

# Database Backup and Branching

`JSONLiteDB.backup()` copies a database using SQLite's [online backup API][back]. The destination can be a path, an `sqlite3.Connection`, or another `JSONLiteDB` instance.

[back]: https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup

```python exe
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonlitedb import JSONLiteDB
```

## Copy to another database

Create an in-memory database and populate it:

```python exe
source = JSONLiteDB.memory()
source.insert(
    {"first": "John", "last": "Lennon", "role": "guitar"},
    {"first": "Paul", "last": "McCartney", "role": "bass"},
    {"first": "George", "last": "Harrison", "role": "guitar"},
    {"first": "Ringo", "last": "Starr", "role": "drums"},
)
```

Back it up directly to another `JSONLiteDB` instance:

```python exe
copy = JSONLiteDB.memory()
source.backup(copy)
copy.query(_orderby="first").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'first': 'John', 'last': 'Lennon', 'role': 'guitar'},
 {'first': 'Paul', 'last': 'McCartney', 'role': 'bass'},
 {'first': 'Ringo', 'last': 'Starr', 'role': 'drums'}]
```
<!-- md-demo: result end -->
The backup is an independent database. Later changes do not affect the source:

```python exe
copy.delete(first="Ringo")
print(f"{source.count() = }")
print(f"{copy.count() = }")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
source.count() = 4
copy.count() = 3
```
<!-- md-demo: result end -->
## Back up to a file

A path can be passed directly; there is no need to open or close a separate SQLite connection:

```python exe
tmpdir = TemporaryDirectory()
backup_path = Path(tmpdir.name) / "backup.db"

source.backup(backup_path)
saved = JSONLiteDB.read_only(backup_path)
print(f"{saved.count() = }")
saved.close()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
saved.count() = 4
```
<!-- md-demo: result end -->
## Branch and continue from the backup

With `reopen=True`, the object switches to the destination after copying. This is useful for branching a file-backed database into memory before making temporary changes:

```python exe
original_path = Path(tmpdir.name) / "original.db"
working = JSONLiteDB(original_path)
working.insert({"version": "original"})

working.backup(":memory:", reopen=True)
working.insert({"version": "temporary"})

original = JSONLiteDB.read_only(original_path)
print(f"{original.count() = }")
print(f"{working.count() = }")
print(working)

original.close()
working.close()
source.close()
copy.close()
tmpdir.cleanup()
```
<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
original.count() = 1
working.count() = 2
JSONLiteDB(':memory:')
```
<!-- md-demo: result end -->
