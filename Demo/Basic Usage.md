<!-- md-demo
setup: |
  import init_demo_mode
-->

## Basic Usage

With some fake data.

```python exe
import jsonlitedb
from jsonlitedb import JSONLiteDB

print(f"{jsonlitedb.__version__ = }")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
jsonlitedb.__version__ = '0.5.2'
```
<!-- md-demo: result end -->
```python exe
db = JSONLiteDB(":memory:")
# more generally:
# db = JSONLiteDB('my_data.db')
```

Insert some data. Can use `insert()` with any number of items or `insertmany()` with an iterable (`insertmany([...]) <--> insert(*[...])`).

Can also use a context manager (`with db: ...`) to batch the insertions (or deletions).

```python exe
db.insert(
    {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
    {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
    {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
    {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
    {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
)
```

```python exe
len(db)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
5
```
<!-- md-demo: result end -->
```python exe
list(db)
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
### Simple Queries

Let's do some simple queries. The default `query()` returns an iterator so we can wrap them in a list or `.all()`.

```python exe
db.query(first="George").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
When you only want one, you can do `db.query(...).one()` but that still queries all. Instead, use `db.one()`. On the SQL call, this adds `LIMIT 1`

```python exe
db.one(first="George", last="Martin")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}
```
<!-- md-demo: result end -->
Now let's query with a dictionary to match.

Queries return a QueryResult which can be iterated. list(QueryResult) <==> QueryResult.all()

```python exe
list(db.query({"first": "George"}))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
Multiples are always an AND query. See Query Objects below for more flexibility.

```python exe
db.query({"first": "George", "last": "Martin"}).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
Can do seperate items but it makes no difference. The dictionaries are unioned.

```python exe
db.query({"first": "George"}, {"last": "Martin"}).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
If all you need is the count, use `db.count(...)` instead of counting the results. This does that count at the SQL level.

```python exe
db.count(first="George")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
2
```
<!-- md-demo: result end -->
### Query Objects

Query objects enable more complex combinations and inequalities. Query objects can be from the database (`db.Query` or `db.Q`) or created on thier own (`Query()` or `Q()`). They are all the same.

```python exe
db.query(db.Q.first == "George").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
Note that you **need to be careful with parentheses** as the operator precedance for the `&` and `|` are very high!

```python exe
db.query((db.Q.first == "George") & (db.Q.last == "Martin")).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
You can also use a more fluent approach with `.and_()`, `or_()`, and `.not_()`

```python exe
db.query((db.Q.first == "George").and_(db.Q.last == "Martin")).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
Can do inequalities too

```python exe
db.query(db.Q.born < 1930).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
Queries support: `==`, `!=`, `<`, `<=`, `>`, `>=` for normal comparisons.

In addition they support

- `%` : `LIKE`
- `*` : `GLOB`
- `@` : `REGEXP` using Python's regex module. Note that this is DISABLED by default

```python exe
# This will all be the same
db.query(db.Q.role % "prod%").all()  # LIKE
db.query(db.Q.role * "prod*").all()  # GLOB
db.query(db.Q.role @ "prod").all()  # REGEXP -- Python based
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
### Sorting / Ordering

JSONLiteDB supports `_orderby` on `query()` and helpers that wrap it, such as `one()` and `count()` (see Advanced Usage).

The input is effectively the same as a query path, but it does not include a value and can use "+" for ascending order (the default) or "-" for descending order. See the help for `query()` for more details, including how ordering works with the different path forms. There is also a special `db.Q.rowid_` object you can use for sorting.

```python exe
db.query(db.Q.first == "George").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
```python exe
db.query(db.Q.first == "George", _orderby="-role").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'},
 {'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'}]
```
<!-- md-demo: result end -->
```python exe
db.query(_orderby=[-db.Q.role, db.Q.last]).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'},
 {'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'born': 1940, 'first': 'John', 'last': 'Lennon', 'role': 'guitar'},
 {'born': 1940, 'first': 'Ringo', 'last': 'Starr', 'role': 'drums'},
 {'born': 1942, 'first': 'Paul', 'last': 'McCartney', 'role': 'bass'}]
```
<!-- md-demo: result end -->
You can sort by subkeys and subelements as well with a similar syntax to queries. See `query()` for more details.

### Speeding up queries

Queries can be **greatly accelerated** with an index. Note that SQLite is *extremely* picky about how you write the index! For the most part, if you use the same path form for the query and the index, you will be fine. (This is more of an issue with nested queries and *advanced* query formulations.)

The name of the index is immaterial. It is derived from the fields, so it may look different from these examples.

```python exe
db.create_index("last")
db.indexes
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{'ix_items_1bd45eb5': ['$."last"']}
```
<!-- md-demo: result end -->
Of course, with four items, this makes little difference but can **greatly accelerate** hot query paths.

```python exe
list(db.query(last="Martin"))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[{'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
And an index can also be used to enforce uniqueness amongst one or more fields

```python exe
db.create_index("first", "last", unique=True)
db.indexes
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{'ix_items_1bd45eb5': ['$."last"'],
 'ix_items_250e4243_UNIQUE': ['$."first"', '$."last"']}
```
<!-- md-demo: result end -->
```python exe
# db.insert({'first': 'George', 'last': 'Martin', 'type':'FAKE ENTRY'})
# Causes: IntegrityError: UNIQUE constraint failed: index 'ix_items_250e4243_UNIQUE'
```

See *Advanced Usage* for more examples including nested queries and more complex logic.
