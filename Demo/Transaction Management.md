<!-- md-demo
setup: |
  import os
  os.environ["JSONLiteDB_SQL_DEBUG"] = "true"
  import init_demo_mode
-->

# Transaction Management

Generally, SQLiteDB tries to manage transactions to be as efficient as possible. When methods allow for multiple actions (e.g. `insertmany(items)` or `insert(*items)`) it uses `sqlite3`'s optimized interface. But other actions can be improved using the context manager.

## Aside: Logging SQL Statements

SQL statements can be debug-logged with its own Python logger. This is turned off by default as it is beyond even DEBUG level information but can be turned on with the `JSONLiteDB_SQL_DEBUG` environment variable.

```python exe
import logging
```

Now turn on logging the SQL calls.

```python exe
logging.basicConfig(level=logging.DEBUG)
```

```python exe
import jsonlitedb
from jsonlitedb import JSONLiteDB, Q
```

```python exe
db = JSONLiteDB(":memory:")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb:self.table = 'items'
DEBUG:jsonlitedb.jsonlitedb:DB metadata table missing. Creating schema
DEBUG:jsonlitedb.jsonlitedb-sql:
CREATE TABLE IF NOT EXISTS items(
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT
)
DEBUG:jsonlitedb.jsonlitedb-sql:
CREATE TABLE IF NOT EXISTS items_kv(
    key TEXT PRIMARY KEY,
    val TEXT
)
DEBUG:jsonlitedb.jsonlitedb-sql:PRAGMA journal_mode = wal
```
<!-- md-demo: result end -->
## Inserts

Insert items. There will be duplicates but that is fine for this example. Notice in the output when they are commited

```python exe
items = [
    {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
    {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
    {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
    {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
    {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
]
```

### Optimized

```python exe
db.insert(*items)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Martin", "born": 1926, "role": "producer"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
```python exe
db.insertmany(items)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Martin", "born": 1926, "role": "producer"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
```python exe
with db:
    for item in items:
        db.insert(item)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Martin", "born": 1926, "role": "producer"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
### NOT optimized

Notice it commits after each

```python exe
for item in items:
    db.insert(item)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
INSERT  INTO items (data)
VALUES (JSON('{"first": "George", "last": "Martin", "born": 1926, "role": "producer"}'))

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
## Removals

### Optimized

```python exe
row_ids = [row.rowid for row in db.query(db.Q.last == "Martin")]
db.delete_by_rowid(*row_ids)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:
SELECT rowid, data FROM items 
WHERE
    ( JSON_EXTRACT(data, '$."last"') = 'Martin' )



DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 5

DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 10

DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 15

DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 20

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
```python exe
row_ids = [row.rowid for row in db.query(db.Q.last == "Starr")]
with db:
    for row_id in row_ids:
        db.delete_by_rowid(row_id)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:
SELECT rowid, data FROM items 
WHERE
    ( JSON_EXTRACT(data, '$."last"') = 'Starr' )



DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 4

DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 9

DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 14

DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 19

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
Of course, you can bulk delete by the query which will delete all matching items and not even be in the loop

```python exe
db.delete(db.Q.last == "Harrison")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    ( JSON_EXTRACT(data, '$."last"') = 'Harrison' )

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
### Not optimized

```python exe
row_ids = [row.rowid for row in db.query(db.Q.last == "McCartney")]
for row_id in row_ids:
    db.delete_by_rowid(row_id)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
DEBUG:jsonlitedb.jsonlitedb-sql:
SELECT rowid, data FROM items 
WHERE
    ( JSON_EXTRACT(data, '$."last"') = 'McCartney' )



DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 2

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 7

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 12

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
DEBUG:jsonlitedb.jsonlitedb-sql:BEGIN 
DEBUG:jsonlitedb.jsonlitedb-sql:
DELETE FROM items 
WHERE
    rowid = 17

DEBUG:jsonlitedb.jsonlitedb-sql:COMMIT
```
<!-- md-demo: result end -->
```python exe
list(db)
```
<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1940, 'first': 'John', 'last': 'Lennon', 'role': 'guitar'},
 {'born': 1940, 'first': 'John', 'last': 'Lennon', 'role': 'guitar'},
 {'born': 1940, 'first': 'John', 'last': 'Lennon', 'role': 'guitar'},
 {'born': 1940, 'first': 'John', 'last': 'Lennon', 'role': 'guitar'}]
DEBUG:jsonlitedb.jsonlitedb-sql:SELECT rowid, data FROM items
DEBUG:jsonlitedb.jsonlitedb-sql:SELECT COUNT(rowid) FROM items
```
<!-- md-demo: result end -->
