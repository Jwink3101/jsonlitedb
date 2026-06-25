<!-- md-demo
setup: |
  import init_demo_mode
preface-text: "`Out:`"
-->

# Query Functions

Query paths can be passed through SQLite scalar functions before comparison or
sorting. JSONLiteDB provides `lower_()` and `length_()` for common operations,
and `wrap_()` for other scalar functions.

```python exe
import json

from jsonlitedb import JSONLiteDB

db = JSONLiteDB(":memory:")
db.insert(
    {
        "name": "  Alpha",
        "created": "2024-06-01 12:00:00",
        "start": "2024-06-01 12:00:00",
        "end": "2024-06-02 12:00:00",
    },
    {
        "name": "beta  ",
        "created": "2025-01-02 03:04:05",
        "start": "2025-01-03 12:00:00",
        "end": "2025-01-02 12:00:00",
    },
    {
        "name": " Gamma ",
        "created": "2026-03-04 05:06:07",
        "start": "2026-03-04 05:06:07",
        "end": "2026-03-05 05:06:07",
    },
)
```

## Convenience functions

`lower_()` and `length_()` apply SQLite's `LOWER()` and `LENGTH()` functions.
They can be used for comparisons, sorting, and expression indexes.

```python exe
[row["name"] for row in db.query(db.Q.name.lower_() % "%alpha%")]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
['  Alpha']
```
<!-- md-demo: result end -->
```python exe
[row["name"] for row in db.query(_orderby=db.Q.name.length_())]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
['beta  ', '  Alpha', ' Gamma ']
```
<!-- md-demo: result end -->
## General scalar functions

`wrap_()` accepts a SQLite scalar-function name followed by literal arguments.
The extracted JSON value is the first argument unless positioned explicitly.

```python exe
cutoff = 1735689600
[row["name"] for row in db.query(db.Q.created.wrap_("unixepoch") >= cutoff)]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
['beta  ', ' Gamma ']
```
<!-- md-demo: result end -->
Additional arguments follow the extracted value. This applies
`SUBSTR(value, 1, 7)`:

```python exe
[row["created"] for row in db.query(db.Q.created.wrap_("substr", 1, 7) == "2025-01")]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
['2025-01-02 03:04:05']
```
<!-- md-demo: result end -->
Use `db.Q.VALUE_` when the extracted value is not the first argument. This
applies `STRFTIME('%Y', value)`:

```python exe
[row["name"] for row in db.query(
    db.Q.created.wrap_("strftime", "%Y", db.Q.VALUE_) == "2026"
)]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[' Gamma ']
```
<!-- md-demo: result end -->
Function calls can be composed. They are applied from left to right:

```python exe
[row["name"] for row in db.query(_orderby=db.Q.name.wrap_("trim").lower_())]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
['  Alpha', 'beta  ', ' Gamma ']
```
<!-- md-demo: result end -->
The function name must be a simple SQL identifier. All other arguments are
treated as literal values and escaped using the same SQLite-based quoting
helper used for JSON paths. `wrap_()` does not accept raw SQL or other query
objects as arguments. JSONLiteDB does not maintain a function allowlist or
pre-check argument counts; SQLite reports unknown functions, invalid argument
counts, and other execution errors.

As with the existing path transforms, `wrap_()` is not supported on wildcard
paths such as `db.Q.items[:]`, on `db.Q.rowid_`, or after a comparison has
already built a query. Since `VALUE_` is reserved, use bracket notation for a
JSON key with that exact name:

```python
db.Q["VALUE_"]
```

## Expression indexes

Wrapped paths can be indexed when SQLite considers the resulting expression
deterministic:

```python exe
month = db.Q.created.wrap_("substr", 1, 7)
db.create_index(month)
db.indexes
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'ix_items_0f4006b6': ['SUBSTR($."created", 1, 7)']}
```
<!-- md-demo: result end -->
Use the same wrapped expression when querying so SQLite can match the
expression index:

```python exe
db.explain_query(month == "2025-01")[0]["detail"]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
'SEARCH items USING INDEX ix_items_0f4006b6 (<expr>=?)'
```
<!-- md-demo: result end -->
SQLite decides whether a particular function expression is legal in an index.
Some date/time modifiers may be rejected as non-deterministic even though the
same expression is valid in a normal query.

## When to use SQLite directly

`wrap_()` transforms the JSON path on the left side of a JSONLiteDB
comparison. It intentionally does not build arbitrary expressions on the
right side.

For example, to have SQLite transform a bound comparison value, use
parameterized SQL:

```python exe
new_date = "2025-01-01 00:00:00"
rows = db.execute(
    """
    SELECT data
    FROM items
    WHERE unixepoch(JSON_EXTRACT(data, '$."created"')) >= unixepoch(?)
    ORDER BY unixepoch(JSON_EXTRACT(data, '$."created"'))
    """,
    (new_date,),
)
[json.loads(row["data"])["name"] for row in rows]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
['beta  ', ' Gamma ']
```
<!-- md-demo: result end -->
Another common case is comparing two dates from the same row. For example,
you may want to find records where `start` is before `end`. Conceptually, the
unsupported query would be:

```python
db.Q.start.wrap_("unixepoch") < db.Q.end.wrap_("unixepoch")
```

JSONLiteDB comparisons treat the right side as a literal value, not another
SQL expression. Use direct SQL when both JSON paths need transformation:

```python exe
rows = db.execute(
    """
    SELECT data
    FROM items -- Or table name
    WHERE 
        unixepoch(JSON_EXTRACT(data, '$."start"'))
        < 
        unixepoch(JSON_EXTRACT(data, '$."end"'))
    ORDER BY rowid
    """
)
[json.loads(row["data"])["name"] for row in rows]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
['  Alpha', ' Gamma ']
```
<!-- md-demo: result end -->
Continue to bind external values with `?` parameters. Do not interpolate them
into SQL strings.
