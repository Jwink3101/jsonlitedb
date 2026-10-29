<!-- md-demo
setup: |
  import init_demo_mode
-->

# Importing and Exporting Data

JSONLiteDB can exchange data with JSON Lines files through `export_jsonl()` and `import_jsonl()`. The latter is an alias for `load_jsonl()`. Use `load_json()` for a complete JSON document or array of documents.

```python exe
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonlitedb import JSONLiteDB

tmpdir = TemporaryDirectory()
data_dir = Path(tmpdir.name)
```

## Export and Restore JSON Lines

Each document is written as one JSON value per line:

```python exe
source = JSONLiteDB.memory()
source.insert(
    {"id": 1, "name": "alpha"},
    {"id": 2, "name": "beta"},
)

jsonl_path = data_dir / "items.jsonl"
source.export_jsonl(jsonl_path)
print(jsonl_path.read_text(), end="")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{"id":1,"name":"alpha"}
{"id":2,"name":"beta"}
```
<!-- md-demo: result end -->
Importing that file restores the documents. Duplicate handling uses the same options as `insert()` and `insertmany()`:

```python exe
restored = JSONLiteDB.memory()
restored.import_jsonl(jsonl_path)
restored.create_index("id", unique=True)

# Importing the same file again would violate the unique index, so ignore it.
restored.import_jsonl(jsonl_path, duplicates="ignore")
restored.query(_orderby="id").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'id': 1, 'name': 'alpha'}, {'id': 2, 'name': 'beta'}]
```
<!-- md-demo: result end -->
## Import Regular JSON

`load_json()` accepts a path or file-like object containing either one document or an array of documents:

```python exe
json_path = data_dir / "items.json"
json_path.write_text(
    json.dumps(
        [
            {"id": 3, "name": "gamma"},
            {"id": 4, "name": "delta"},
        ]
    )
)

from_json = JSONLiteDB.memory()
from_json.load_json(json_path)
from_json.query(_orderby="id").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'id': 3, 'name': 'gamma'}, {'id': 4, 'name': 'delta'}]
```
<!-- md-demo: result end -->
## Work with JSON Strings

By default, writes encode Python objects as JSON and reads decode JSON into Python objects. Use `_raw=True` when supplying or retrieving JSON strings. SQLite still processes the JSON, so formatting may change. Raw results do not carry a `rowid` attribute; supply the rowid explicitly when updating them.

```python exe
raw_db = JSONLiteDB.memory()
raw_db.insert('{"id":1,"name":"alpha"}', _raw=True)
raw_db.insertmany(['{"id":2,"name":"beta"}'], _raw=True)

print(raw_db.query_one(id=1))
print(raw_db.query_one(id=1, _raw=True))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{'id': 1, 'name': 'alpha'}
{"id":1,"name":"alpha"}
```
<!-- md-demo: result end -->
`_raw=True` also works with `items()`, `get_by_rowid()`, `update()`, `update_many()`, and `patch()`:

```python exe
rowid = raw_db.query_one(id=1).rowid
raw_db.update('{"id":1,"name":"updated"}', rowid=rowid, _raw=True)
raw_db.update_many([('{"id":2,"name":"second"}', 2)], _raw=True)
raw_db.patch('{"active":true}', id=1, _raw=True)
print(raw_db.get_by_rowid(rowid, _raw=True))
print(list(raw_db.items(_raw=True)))
raw_db.close()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{"id":1,"name":"updated","active":true}
['{"id":1,"name":"updated","active":true}', '{"id":2,"name":"second"}']
```
<!-- md-demo: result end -->
## Import a File-Like Object

File-like objects are useful for data already in memory or supplied by another library:

```python exe
stream = StringIO('{"id":5,"name":"epsilon"}\n')
from_json.import_jsonl(stream)
from_json.query_one(id=5)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{'id': 5, 'name': 'epsilon'}
```
<!-- md-demo: result end -->
```python exe
source.close()
restored.close()
from_json.close()
tmpdir.cleanup()
```
