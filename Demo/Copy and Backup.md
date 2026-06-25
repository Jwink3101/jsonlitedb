<!-- md-demo
setup: |
  import init_demo_mode
-->

# Database Copy and Backup

A quick example of using [sqlite3 backup][back] methods to copy and backup databases.

These work because you can specify an `sqlite3.Connection` object to instantiate JSONLiteDB

[back]:https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup

```python exe
import os

from jsonlitedb import JSONLiteDB
```

```python exe
import sqlite3
import subprocess
```

```python exe
db0 = JSONLiteDB(":memory:")
print(db0)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
JSONLiteDB(':memory:')
```
<!-- md-demo: result end -->
```python exe
db0.insert(
    {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
    {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
    {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
    {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
    {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
)
```

Copy it by createing a new database connection

```python exe
# TMP sqlite3 connection
_db1 = sqlite3.connect(":memory:")

# Use the underlying sqlite3.Connection object of db0 to backup
db0.db.backup(_db1)

# create a new database
db1 = JSONLiteDB(_db1)
print(db1)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
JSONLiteDB('*existing connection*')
```
<!-- md-demo: result end -->
```python exe
list(db1)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1940, 'first': 'John', 'last': 'Lennon', 'role': 'guitar'},
 {'born': 1942, 'first': 'Paul', 'last': 'McCartney', 'role': 'bass'},
 {'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'born': 1940, 'first': 'Ringo', 'last': 'Starr', 'role': 'drums'},
 {'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
Demonstrate that they are not the same underlying database

```python exe
db1.delete(last="Martin")
print(f"{db0.count(last='Martin') = }")
print(f"{db1.count(last='Martin') = }")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
db0.count(last='Martin') = 1
db1.count(last='Martin') = 0
```
<!-- md-demo: result end -->
The same approach can be used to save an in-memory database too

```python exe
try:  # Just to make sure it gets cleared
    dbfile = sqlite3.connect("mydb.db")
    db0.db.backup(dbfile)
    dbfile.close()

    print(f"{os.path.exists('mydb.db') = }")

    db2 = JSONLiteDB("mydb.db")
    print(f"{len(db2) = }")

    print(subprocess.check_output(["sqlite3", "mydb.db", ".dump"]).decode())
finally:
    pass  # os.unlink('mydb.db') # This will also fail if mydb.db didn't exist
```
<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
os.path.exists('mydb.db') = True
len(db2) = 5
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE items(
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT
);
INSERT INTO items VALUES(1,'{"first":"John","last":"Lennon","born":1940,"role":"guitar"}');
INSERT INTO items VALUES(2,'{"first":"Paul","last":"McCartney","born":1942,"role":"bass"}');
INSERT INTO items VALUES(3,'{"first":"George","last":"Harrison","born":1943,"role":"guitar"}');
INSERT INTO items VALUES(4,'{"first":"Ringo","last":"Starr","born":1940,"role":"drums"}');
INSERT INTO items VALUES(5,'{"first":"George","last":"Martin","born":1926,"role":"producer"}');
CREATE TABLE items_kv(
    key TEXT PRIMARY KEY,
    val TEXT
);
DELETE FROM sqlite_sequence;
INSERT INTO sqlite_sequence VALUES('items',5);
COMMIT;

```
<!-- md-demo: result end -->
