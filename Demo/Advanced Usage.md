<!-- md-demo
setup: |
  import init_demo_mode
preface-text: "`Out:`"
-->

# Advanced Usage

Some more complex usages and tools

```python exe
import jsonlitedb
from jsonlitedb import JSONLiteDB, Q

print(f"{jsonlitedb.__version__ = }")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
jsonlitedb.__version__ = '0.5.2'
```
<!-- md-demo: result end -->
```python exe
import sqlite3
import json
```

## Nested Dictionaries

One advantage of JSONLiteDB is that it can query *into* a nested dictionary. Consider the following: (obviosly, in real usages, there would be many more items)

```python exe
db = JSONLiteDB(":memory:")
with db:  # Not needed but batches the insertion
    db.insert(
        {
            "first": "John",
            "last": "Smith",
            "age": 40,
            "phone": {"home": "215.555.6587", "work": "919.555.4795"},
            "kids": [
                {"first": "John Jr.", "last": "Smith"},
                {"first": "Jane", "last": "Smith"},
            ],
            "hobbies": ["reading"],
        }
    )
    db.insert(
        {
            "first": "Clark",
            "last": "Drake",
            "age": 26,
            "phone": {"home": "412.555.4960", "work": "410.555.9903"},
            "kids": [],
            "hobbies": ["travel", "running", "reading"],
        }
    )
    db.insert(
        {
            "first": "Peggy",
            "last": "Line",
            "age": 34,
            "phone": {"home": "505.555.3101"},
            "kids": [
                {"first": "Jane", "last": "Line"},
                {"first": "Molly", "last": "Line"},
            ],
            "hobbies": [],
        }
    )
    db.insert(
        {
            "first": "Luke",
            "last": "Truss",
            "age": 30,
            "phone": {"home": "610.555.2647"},
            "kids": [{"first": "Janet", "last": "Truss"}],
            "hobbies": ["hiking"],
        }
    )
```

All of these have **identical results**

```python exe
# Using a tuple
a = db.query({("phone", "home"): "505.555.3101"}).all()

# Quoted JSON path. See below for discussion and comments on quoting
b = db.query({'$."phone"."home"': "505.555.3101"}).all()

# Query Objects
c = db.query(db.Q.phone.home == "505.555.3101").all()

a == b == c
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
True
```
<!-- md-demo: result end -->
This is also **identical** but since this is `"$.phone.home"` and the others result in `'$."phone"."home"'` an index built with one will not be used with the other.

```python exe
# Using the SQLite JSON path style.
db.query({"$.phone.home": "505.555.3101"}).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}}]
```
<!-- md-demo: result end -->
Of course, using a query object allows for even more flexibility: Use a LIKE

```python exe
db.query(db.Q.phone.home % "505%").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}}]
```
<!-- md-demo: result end -->
Notice these all return a list because of `.all()`. Can also do:

```python exe
db.one(db.Q.phone.home % "505%")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'age': 34,
 'first': 'Peggy',
 'hobbies': [],
 'kids': [{'first': 'Jane', 'last': 'Line'},
          {'first': 'Molly', 'last': 'Line'}],
 'last': 'Line',
 'phone': {'home': '505.555.3101'}}
```
<!-- md-demo: result end -->
```python exe
db.query(db.Q.phone.home % "505%").one()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'age': 34,
 'first': 'Peggy',
 'hobbies': [],
 'kids': [{'first': 'Jane', 'last': 'Line'},
          {'first': 'Molly', 'last': 'Line'}],
 'last': 'Line',
 'phone': {'home': '505.555.3101'}}
```
<!-- md-demo: result end -->
Note that `db.one(...)` and `db.query(...).one()` should return the same thing but the former is more efficient because it adds a LIMIT clause. Can also do:

```python exe
db.query(db.Q.phone.home % "505%", _limit=1).one()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'age': 34,
 'first': 'Peggy',
 'hobbies': [],
 'kids': [{'first': 'Jane', 'last': 'Line'},
          {'first': 'Molly', 'last': 'Line'}],
 'last': 'Line',
 'phone': {'home': '505.555.3101'}}
```
<!-- md-demo: result end -->
### rowid

Every returned item is basically a dict with the addition of the `rowid` property

```python exe
type(db.query_one(db.Q.phone.home % "505%"))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
<class 'jsonlitedb.jsonlitedb.DBDict'>
```
<!-- md-demo: result end -->
```python exe
db.query_one(db.Q.phone.home % "505%").rowid
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
3
```
<!-- md-demo: result end -->
And you can get items by rowid

```python exe
db[3]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'age': 34,
 'first': 'Peggy',
 'hobbies': [],
 'kids': [{'first': 'Jane', 'last': 'Line'},
          {'first': 'Molly', 'last': 'Line'}],
 'last': 'Line',
 'phone': {'home': '505.555.3101'}}
```
<!-- md-demo: result end -->
### Lists of Items (i.e. Array Queries)

You can also query from a list element given the zero-based index.

Find any whos *first* kid is named 'Jane'. Both of the following are the same:

```python exe
list(db.query({("kids", 0, "first"): "Jane"}))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}}]
```
<!-- md-demo: result end -->
```python exe
list(db.query(db.Q.kids[0].first == "Jane"))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}}]
```
<!-- md-demo: result end -->
You can use **array queries** to find if *any* kid is named Jane. By passing a slice `[:]` it will use a different SQLite structure (`JSON_EACH` and other conditionals to ensure it is an array)

```python exe
db.query(db.Q.kids[:].first == "Jane").all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}},
 {'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}}]
```
<!-- md-demo: result end -->
These can be combined as usual

```python exe
db.query((db.Q.kids[:].first == "Jane") & (db.Q.hobbies[:] == "reading")).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}}]
```
<!-- md-demo: result end -->
```python exe
db.query((db.Q.kids[:].first == "Jane").and_(db.Q.age < 38)).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}}]
```
<!-- md-demo: result end -->
```python exe
db.count((db.Q.kids[:].first == "Jane").and_(db.Q.age < 38))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
1
```
<!-- md-demo: result end -->
### Keys/Paths

We can also look into the items more. Recall that in these examples, there are lots of common keys but there doesn't have to be!

For this demo, let's first add some new items

```python exe
db.insert({"new": "item", "and_with": {"multiple": "sub", "elements": None}})
```

Can see how often certains keys show

```python exe
db.path_counts()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'age': 4,
 'and_with': 1,
 'first': 4,
 'hobbies': 4,
 'kids': 4,
 'last': 4,
 'new': 1,
 'phone': 4}
```
<!-- md-demo: result end -->
```python exe
db.keys()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
dict_keys(['age', 'first', 'hobbies', 'kids', 'last', 'phone', 'and_with', 'new'])
```
<!-- md-demo: result end -->
Same for subkeys. These follow the standard options of JSON path string, regular single-item key, tuple, or query objects

Notice this is empty because there are no sub-elements to `'new'`

```python exe
db.path_counts("new")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{}
```
<!-- md-demo: result end -->
But there are sub items for `and_with`

```python exe
db.path_counts(db.Q.and_with)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'elements': 1, 'multiple': 1}
```
<!-- md-demo: result end -->
```python exe
db.keys(db.Q.and_with)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
dict_keys(['elements', 'multiple'])
```
<!-- md-demo: result end -->
#### Queries if paths exists

JSONLiteDB, and the underlying tools, treat items as if they contain every path with a default value of `None`. Normally this is fine since you can do something like:

```python exe
list(db.query(db.Q.new != None))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'and_with': {'elements': None, 'multiple': 'sub'}, 'new': 'item'}]
```
<!-- md-demo: result end -->
But for the path `db.Q.and_with.elements`, the value *is* None

```python exe
list(db.query(db.Q.and_with.elements != None))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[]
```
<!-- md-demo: result end -->
You can use `Q.<...>.exists_()` or `Q.<...>.missing_()`

```python exe
db.query(db.Q.and_with.elements.exists_()).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'and_with': {'elements': None, 'multiple': 'sub'}, 'new': 'item'}]
```
<!-- md-demo: result end -->
```python exe
db.count(db.Q.and_with.elements.missing_())
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
4
```
<!-- md-demo: result end -->
**Deprecated compatibility helper**:

`query_by_path_exists()` remains available for older code, but new code should prefer `.exists_()` so path-existence checks can be composed with other queries.

```python exe
# Deprecated compatibility helper
list(db.query_by_path_exists(db.Q.and_with.elements))
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'and_with': {'elements': None, 'multiple': 'sub'}, 'new': 'item'}]
```
<!-- md-demo: result end -->
## Sorting

These demonstrate more advanced sorting methods and specification, including subkeys.

**Reminder**: Like creating an index (see below), the exact for *does* matter. `$.key` and `$."key"` are *functionally* the same will be not use each other's index.

**Note**: missing keys are sorted first as per how SQLite works.

```python exe
list(db)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}},
 {'age': 26,
  'first': 'Clark',
  'hobbies': ['travel', 'running', 'reading'],
  'kids': [],
  'last': 'Drake',
  'phone': {'home': '412.555.4960', 'work': '410.555.9903'}},
 {'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}},
 {'age': 30,
  'first': 'Luke',
  'hobbies': ['hiking'],
  'kids': [{'first': 'Janet', 'last': 'Truss'}],
  'last': 'Truss',
  'phone': {'home': '610.555.2647'}},
 {'and_with': {'elements': None, 'multiple': 'sub'}, 'new': 'item'}]
```
<!-- md-demo: result end -->
```python exe
db.query(_orderby=db.Q.phone.home).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'and_with': {'elements': None, 'multiple': 'sub'}, 'new': 'item'},
 {'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}},
 {'age': 26,
  'first': 'Clark',
  'hobbies': ['travel', 'running', 'reading'],
  'kids': [],
  'last': 'Drake',
  'phone': {'home': '412.555.4960', 'work': '410.555.9903'}},
 {'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}},
 {'age': 30,
  'first': 'Luke',
  'hobbies': ['hiking'],
  'kids': [{'first': 'Janet', 'last': 'Truss'}],
  'last': 'Truss',
  'phone': {'home': '610.555.2647'}}]
```
<!-- md-demo: result end -->
Notice the missing key is sorted first. You can add a query or use `.exists_()` to filter for documents where the path exists. The difference between `!= None` and `.exists_()` is whether a key set to `None` is included. In this example, it doesn't matter.

```python exe
db.query(db.Q.first != None, _orderby=db.Q.phone.home).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}},
 {'age': 26,
  'first': 'Clark',
  'hobbies': ['travel', 'running', 'reading'],
  'kids': [],
  'last': 'Drake',
  'phone': {'home': '412.555.4960', 'work': '410.555.9903'}},
 {'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}},
 {'age': 30,
  'first': 'Luke',
  'hobbies': ['hiking'],
  'kids': [{'first': 'Janet', 'last': 'Truss'}],
  'last': 'Truss',
  'phone': {'home': '610.555.2647'}}]
```
<!-- md-demo: result end -->
```python exe
db.query(db.Q.first.exists_() & (db.Q.last != "Drake"), _orderby=db.Q.phone.home).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}},
 {'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}},
 {'age': 30,
  'first': 'Luke',
  'hobbies': ['hiking'],
  'kids': [{'first': 'Janet', 'last': 'Truss'}],
  'last': 'Truss',
  'phone': {'home': '610.555.2647'}}]
```
<!-- md-demo: result end -->
```python exe
db.query(db.Q.first.exists_(), _orderby=db.Q.phone.home).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}},
 {'age': 26,
  'first': 'Clark',
  'hobbies': ['travel', 'running', 'reading'],
  'kids': [],
  'last': 'Drake',
  'phone': {'home': '412.555.4960', 'work': '410.555.9903'}},
 {'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}},
 {'age': 30,
  'first': 'Luke',
  'hobbies': ['hiking'],
  'kids': [{'first': 'Janet', 'last': 'Truss'}],
  'last': 'Truss',
  'phone': {'home': '610.555.2647'}}]
```
<!-- md-demo: result end -->
Using other specification forms:

```python exe
db.query(db.Q.first != None, _orderby=("-phone", "home")).all()
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'age': 30,
  'first': 'Luke',
  'hobbies': ['hiking'],
  'kids': [{'first': 'Janet', 'last': 'Truss'}],
  'last': 'Truss',
  'phone': {'home': '610.555.2647'}},
 {'age': 34,
  'first': 'Peggy',
  'hobbies': [],
  'kids': [{'first': 'Jane', 'last': 'Line'},
           {'first': 'Molly', 'last': 'Line'}],
  'last': 'Line',
  'phone': {'home': '505.555.3101'}},
 {'age': 26,
  'first': 'Clark',
  'hobbies': ['travel', 'running', 'reading'],
  'kids': [],
  'last': 'Drake',
  'phone': {'home': '412.555.4960', 'work': '410.555.9903'}},
 {'age': 40,
  'first': 'John',
  'hobbies': ['reading'],
  'kids': [{'first': 'John Jr.', 'last': 'Smith'},
           {'first': 'Jane', 'last': 'Smith'}],
  'last': 'Smith',
  'phone': {'home': '215.555.6587', 'work': '919.555.4795'}}]
```
<!-- md-demo: result end -->
There is also a special way to sort by `rowid` used internally. Note that `rowid` is not a perfect surrogate for insertion order since some methods replace rows.

```python exe
[row.rowid for row in db.query()]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[1, 2, 3, 4, 5]
```
<!-- md-demo: result end -->
```python exe
[row.rowid for row in db.query(_orderby=-db.Q.rowid_)]
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[5, 4, 3, 2, 1]
```
<!-- md-demo: result end -->
## Introspection

```python exe
sql, filler = db.render_query(
    (db.Q.kids[:].first == "Jane").or_(
        (db.Q.age < 38) & (db.Q.hobbies[:] == "reading")
    ),
    _orderby=[-db.Q.age, db.Q.last, db.Q.first],
)

# Fill this in to view
for key, val in filler.items():
    sql = sql.replace(":" + key, jsonlitedb.sqlite_quote(val))
print(sql)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```

            SELECT rowid, data FROM items 
            WHERE
                ( EXISTS (
                    SELECT 1
                    FROM JSON_EACH(data, '$."kids"') AS jldb_each_0
                    WHERE
                        JSON_TYPE(data, '$."kids"') = 'array'
                        AND JSON_EXTRACT(jldb_each_0.value, '$."first"') = 'Jane'
                ) OR ( ( JSON_EXTRACT(data, '$."age"') < 38 ) AND EXISTS (
                    SELECT 1
                    FROM JSON_EACH(data, '$."hobbies"') AS jldb_each_0
                    WHERE
                        JSON_TYPE(data, '$."hobbies"') = 'array'
                        AND jldb_each_0.value = 'reading'
                ) ) )
            ORDER BY
              JSON_EXTRACT(items.data, '$."age"') DESC,
              JSON_EXTRACT(items.data, '$."last"') ASC,
              JSON_EXTRACT(items.data, '$."first"') ASC
            
            
```
<!-- md-demo: result end -->
```python exe
db.explain_query(
    (db.Q.kids[:].first == "Jane").or_(
        (db.Q.age < 38) & (db.Q.hobbies[:] == "reading")
    ),
    _orderby=[-db.Q.age, db.Q.last, db.Q.first],
)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'detail': 'SCAN items', 'id': 3, 'notused': 216, 'parent': 0},
 {'detail': 'CORRELATED SCALAR SUBQUERY 1', 'id': 6, 'notused': 0, 'parent': 0},
 {'detail': 'SCAN jldb_each_0 VIRTUAL TABLE INDEX 3:',
  'id': 13,
  'notused': 0,
  'parent': 6},
 {'detail': 'CORRELATED SCALAR SUBQUERY 2',
  'id': 31,
  'notused': 0,
  'parent': 0},
 {'detail': 'SCAN jldb_each_0 VIRTUAL TABLE INDEX 3:',
  'id': 38,
  'notused': 0,
  'parent': 31},
 {'detail': 'USE TEMP B-TREE FOR ORDER BY',
  'id': 62,
  'notused': 0,
  'parent': 0}]
```
<!-- md-demo: result end -->
## Indexes, Unique Constraints, and Insertions

As mentioned in basic usage, an index can *dramatically* speed up queries. They can also be used to enfore uniqueness.

Consider a simple index:

```python exe
db = JSONLiteDB(":memory:")
db.insert({"make": "Ford", "model": "Mustang", "color": "red", "orders": 15})
db.insert({"make": "Honda", "model": "Accord", "color": "blue", "orders": 35})
db.insert({"make": "Kia", "model": "Telluride", "color": "red", "orders": 8})

db.create_index("color")
db.indexes
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'ix_items_9852c203': ['$."color"']}
```
<!-- md-demo: result end -->
Now we can query by color quickly. What about by make? Use a "unique" index

```python exe
db.drop_index_by_name("ix_items_9852c203")
```

```python exe
db.create_index("make", unique=True)
db.indexes
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'ix_items_e97e5129_UNIQUE': ['$."make"']}
```
<!-- md-demo: result end -->
```python exe
try:
    db.insert({"make": "Ford", "model": "F-150", "color": "green"})
except sqlite3.IntegrityError as E:
    print(f"Raised {type(E).__name__!r}: {E}")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
Raised 'IntegrityError': UNIQUE constraint failed: index 'ix_items_e97e5129_UNIQUE'
```
<!-- md-demo: result end -->
You can ignore it:

```python exe
db.insert({"make": "Ford", "model": "F-150", "color": "green"}, duplicates="ignore")
list(db.query(make="Ford"))  # Unchanged
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'color': 'red', 'make': 'Ford', 'model': 'Mustang', 'orders': 15}]
```
<!-- md-demo: result end -->
or replace it

```python exe
db.insert({"make": "Ford", "model": "F-150", "color": "green"}, duplicates="replace")
list(db.query(make="Ford"))  # Now it's the F-150
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'color': 'green', 'make': 'Ford', 'model': 'F-150'}]
```
<!-- md-demo: result end -->
You can, of coure, delete the index

```python exe
db.drop_index("make")  # or db.drop_index_by_name('ix_items_e97e5129')
```

Note that an index can be on multiple items and/or subqueries. Basically, anything that can be queried, can be made into an index. Do note SQLite is *extremely* particular about the index. An index on `'make'` maps to an index on `'$."make"'` which is functionally the same, but won't be used for a query on `'$.make'`. See below.

```python exe
db.create_index("make")  # Same as db.create_index(db.Q.make)
db.create_index("$.make")  # Functionally the same but different index
db.indexes
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'ix_items_1d9d7315': ['$.make'],
 'ix_items_e97e5129': ['$."make"'],
 'ix_items_e97e5129_UNIQUE': ['$."make"']}
```
<!-- md-demo: result end -->
### Updating Rows

First, note that while the database returns mutable objects (a dict with the `rowid` attribute), it will not save those unless updated!

If those objects are updated, they can be passed back. The `rowid` must either be specified (precendance) or infered from the attribute

```python exe
row = db.query_one(make="Ford")
row["orders"] = 900
db.update(row)

db.query_one(make="Ford")  # Will have 900 orders
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
{'color': 'green', 'make': 'Ford', 'model': 'F-150', 'orders': 900}
```
<!-- md-demo: result end -->
## Aggregate Functions

Data can also be aggregated with AVG COUNT MAX MIN SUM TOTAL either directly or with a method of that name. See https://www.sqlite.org/lang_aggfunc.html for description.

Using the same databse

```python exe
db.AVG("orders")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
314.3333333333333
```
<!-- md-demo: result end -->
```python exe
db.MIN("orders")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
8
```
<!-- md-demo: result end -->
```python exe
db.MAX("orders")
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
900
```
<!-- md-demo: result end -->
```python exe
db.aggregate("orders", "SUM")  # == db.SUM('orders')
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
943
```
<!-- md-demo: result end -->
## Deletions

```python exe
db.delete({"make": "Ford"})
```

Can also do with a context manager to handle multiple in the same transaction

```python exe
with db:
    db.delete({"make": "Honda"})
    db.delete({"make": "Nissan"})
```

And can also delete one or more by rowid if known.

```python exe
rowid = db.query(db.Q.make == "Kia").one().rowid
print(f"{rowid = }")
db.delete_by_rowid(rowid)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
rowid = 3
```
<!-- md-demo: result end -->
## Patch

You can also update items without having to use Python. Consider the following example:

```python exe
db = JSONLiteDB(":memory:")
```

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
db.patch(
    # Define the patch
    {
        "first": "Richard",
        "last": "Starkey",
        "status": "active",  # This is a new field
        "role": None,  # This will be removed.
    },
    # Define the "WHERE" to apply
    (db.Q.last == "Starr"),
)
```

```python exe
list(db)
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
[{'born': 1940, 'first': 'John', 'last': 'Lennon', 'role': 'guitar'},
 {'born': 1942, 'first': 'Paul', 'last': 'McCartney', 'role': 'bass'},
 {'born': 1943, 'first': 'George', 'last': 'Harrison', 'role': 'guitar'},
 {'born': 1940, 'first': 'Richard', 'last': 'Starkey', 'status': 'active'},
 {'born': 1926, 'first': 'George', 'last': 'Martin', 'role': 'producer'}]
```
<!-- md-demo: result end -->
## Recipes

You can build other useful objects out of JSONLiteDB. Either with correct methods to match a Python object or just use it however. Note that there may be ready-made tools that do something similar and that is fine. These just let you use the simple nature of JSONLiteDB.

These examples all use `":memory:"` but the idea is that you can then persist them to a file

### Key-Value Store

Simple as a `{'key':'mykey','value':'myvalue'}` items with a unique index

```python exe
kv = JSONLiteDB(":memory:")
kv.create_index("key", unique=True)

kv.insert({"key": "mykey", "value": "myvalue"})
# ...
```

### List

You could just make object with `None` value but it also works with strings since they are convered to JSON. Adding an index is then an empty tuple

```python exe
mylist = JSONLiteDB(":memory:")
mylist.insert("item1", "item2", "item1")

# mylist.create_index(tuple()) # OPTIONAL
```

```python exe
"item1" in mylist
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
True
```
<!-- md-demo: result end -->
```python exe
"item4" in mylist
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
False
```
<!-- md-demo: result end -->
### Set

Just like a list but create an empty unique index

```python exe
myset = JSONLiteDB(":memory:")
myset.insert("item1", "item2")

myset.create_index(tuple(), unique=True)  # Required to be like a set
```

```python exe
"item1" in myset
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
True
```
<!-- md-demo: result end -->
```python exe
"item3" in myset
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
False
```
<!-- md-demo: result end -->
```python exe
# myset.add('item1')
# IntegrityError: UNIQUE constraint failed: index 'ix_items_c3e97dd6_UNIQUE'
```

## Side Note: Query Objects

Just to note that the following are all the same for a given `db`:

```python exe
db = JSONLiteDB(":memory:")
db.Q.key == "val"  # No call
db.Q().key == "val"  # Called. Optional

from jsonlitedb import Query, Q

Query().key == "val"  # MUST be called
Q().key == "val"  # MUST be called

# See them:
queries = [
    db.Q.key == "val",
    db.Q.key.subkey[3] @ "val",
    db.Q.key.subkey[:] < "val",
    ((db.Q.key == "val").and_(db.Q.key.subkey[:] != "val")).or_(
        ~(db.Q.other[:].subval * "hi*")
    ),
]
for query in queries:
    print(repr(query))
    print("---")
```
<!-- md-demo: result start. Do not edit; this block is overwritten. -->
`Out:`

```
Query(( JSON_EXTRACT(data, '$."key"') = 'val' ))
---
Query(( JSON_EXTRACT(data, '$."key"."subkey"[3]') REGEXP 'val' ))
---
Query(EXISTS (
    SELECT 1
    FROM JSON_EACH(data, '$."key"."subkey"') AS jldb_each_0
    WHERE
        JSON_TYPE(data, '$."key"."subkey"') = 'array'
        AND jldb_each_0.value < 'val'
))
---
Query(( ( ( JSON_EXTRACT(data, '$."key"') = 'val' ) AND EXISTS (
    SELECT 1
    FROM JSON_EACH(data, '$."key"."subkey"') AS jldb_each_0
    WHERE
        JSON_TYPE(data, '$."key"."subkey"') = 'array'
        AND jldb_each_0.value != 'val'
) ) OR ( NOT EXISTS (
    SELECT 1
    FROM JSON_EACH(data, '$."other"') AS jldb_each_0
    WHERE
        JSON_TYPE(data, '$."other"') = 'array'
        AND JSON_EXTRACT(jldb_each_0.value, '$."subval"') GLOB 'hi*'
) ) ))
---
```
<!-- md-demo: result end -->
