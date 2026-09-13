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

## Updates

An outer context keeps repeated `update()` calls in one transaction. `update_many()` also uses one transaction, but it materializes its input before opening that transaction. Thus, the loop streams rows and executes updates individually, while `update_many()` prepares all rows first and then makes one `executemany()` call:

```python exe
logging.getLogger("jsonlitedb.jsonlitedb-sql").disabled = True
logging.getLogger("jsonlitedb.jsonlitedb").disabled = True

def trace_transaction(statement):
    command = statement.split(maxsplit=1)[0]
    if command in {"BEGIN", "COMMIT"}:
        print(command)

loop_db = JSONLiteDB(":memory:")
loop_db.insertmany([{"id": 1}, {"id": 2}])
loop_db.db.set_trace_callback(trace_transaction)

print("update() loop")
with loop_db:
    for row in loop_db:
        row["new"] = "val"
        loop_db.update(row)
        print(f"updated {row['id']}; in transaction: {loop_db.db.in_transaction}")
print(f"after block: {loop_db.db.in_transaction}")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
update() loop
BEGIN
updated 1; in transaction: True
updated 2; in transaction: True
COMMIT
after block: False
```
<!-- md-demo: result end -->
For `map()`, the function must return the modified row; without `return row`, `update_many()` receives `None` and raises `MissingRowIDError`. Its messages appear before `BEGIN`, showing when the iterable is materialized:

```python exe
many_db = JSONLiteDB(":memory:")
many_db.insertmany([{"id": 1}, {"id": 2}])
many_db.db.set_trace_callback(trace_transaction)

def add_value(row):
    row["new"] = "val"
    print(f"prepared {row['id']}")
    return row

print("update_many()")
many_db.update_many(map(add_value, many_db))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
update_many()
prepared 1
prepared 2
BEGIN
COMMIT
```
<!-- md-demo: result end -->
## Rollback on Error

The context manager is also atomic. If an exception escapes the block, SQLite rolls back every change made inside it:

```python exe
db.db.set_trace_callback(None)  # Keep the output focused on rollback behavior.
count_before = db.count()
try:
    with db:
        db.insert({"status": "this will be rolled back"})
        raise RuntimeError("stop the transaction")
except RuntimeError as error:
    print(error)

print(f"{db.count() = }")
print(f"{count_before = }")
```
<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
stop the transaction
db.count() = 4
count_before = 4
```
<!-- md-demo: result end -->
