<!-- md-demo
setup: |
  import init_demo_mode
-->

# Importing and Exporting Data

JSONLiteDB can exchange data with JSON Lines files through `export_jsonl()` and `import_jsonl()`. The latter is an alias for `load_jsonl()` and also reads ordinary `.json` files.

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

A file whose name ends in `.json` can contain either one document or an array of documents:

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
from_json.import_jsonl(json_path)
from_json.query(_orderby="id").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'id': 3, 'name': 'gamma'}, {'id': 4, 'name': 'delta'}]
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
