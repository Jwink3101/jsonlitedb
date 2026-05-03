# JSONLiteDB

SQLite3-backed JSON document database with support for indices and advanced queries.

<img src="logo.svg" alt="Logo" height="250" />

![100% Coverage][100%]

## Premise

JSONLiteDB leverages [SQLite3](https://sqlite.org/index.html) and [JSON1](https://sqlite.org/json1.html) to create a fast JSON document store with easy persistence, indexing capability, and extensible use.

JSONLiteDB provides an easy API with no need to load the entire database into memory, nor dump it when inserting! JSONLiteDB SQLite files are easily usable in other tools with no proprietary formats or encoding. JSONLiteDB is a great replacement for reading a JSON or JSONLines file. Entries can be modified in place. Queries can be indexed for *greatly* improved query speed and optionally to enforce uniqueness.

JSONLiteDB is a nice wrapper and interface to SQLite but there is nothing otherwise proprietary and can be used directly with SQL. 

## Install

From PyPI:

    $ pip install jsonlitedb
    $ pip install jsonlitedb --upgrade
    
Or directly from Github

    $ pip install git+https://github.com/Jwink3101/jsonlitedb.git


<!--- BEGIN AUTO GENERATED -->  
<!--- Auto Generated -->
<!--- DO NOT MODIFY. WILL NOT BE SAVED -->
## Basic Usage

With some fake data.


```python
>>> import jsonlitedb
>>> from jsonlitedb import JSONLiteDB
>>> 
>>> print(f"{jsonlitedb.__version__ = }")
```

    jsonlitedb.__version__ = '0.5.0'



```python
>>> db = JSONLiteDB(":memory:")
>>> # more generally:
>>> # db = JSONLiteDB('my_data.db')
```

Insert some data. Can use `insert()` with any number of items or `insertmany()` with an iterable (`insertmany([...]) <--> insert(*[...])`).

Can also use a context manager (`with db: ...`) to batch the insertions (or deletions).


```python
>>> db.insert(
>>>     {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
>>>     {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
>>>     {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
>>>     {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
>>>     {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
>>> )
```


```python
>>> len(db)
```




    5




```python
>>> list(db)
```




    [{'first': 'John', 'last': 'Lennon', 'born': 1940, 'role': 'guitar'},
     {'first': 'Paul', 'last': 'McCartney', 'born': 1942, 'role': 'bass'},
     {'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'Ringo', 'last': 'Starr', 'born': 1940, 'role': 'drums'},
     {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



### Simple Queries

Let's do some simple queries. The default `query()` returns an iterator so we can wrap them in a list or `.all()`.


```python
>>> db.query(first="George").all()
```




    [{'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



When you only want one, you can do `db.query(...).one()` but that still queries all. Instead, use `db.one()`. On the SQL call, this adds `LIMIT 1`


```python
>>> db.one(first="George", last="Martin")
```




    {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}



Now let's query with a dictionary to match.

Queries return a QueryResult which can be iterated. list(QueryResult) <==> QueryResult.all()


```python
>>> list(db.query({"first": "George"}))
```




    [{'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Multiples are always an AND query. See Query Objects below for more flexibility.


```python
>>> db.query({"first": "George", "last": "Martin"}).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Can do seperate items but it makes no difference. The dictionaries are unioned.


```python
>>> db.query({"first": "George"}, {"last": "Martin"}).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



If all you need is the count, use `db.count(...)` instead of counting the results. This does that count at the SQL level.


```python
>>> db.count(first="George")
```




    2



### Query Objects

Query objects enable more complex combinations and inequalities. Query objects can be from the database (`db.Query` or `db.Q`) or created on thier own (`Query()` or `Q()`). They are all the same. 


```python
>>> db.query(db.Q.first == "George").all()
```




    [{'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Note that you **need to be careful with parentheses** as the operator precedance for the `&` and `|` are very high!


```python
>>> db.query((db.Q.first == "George") & (db.Q.last == "Martin")).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



You can also use a more fluent approach with `.and_()`, `or_()`, and `.not_()`


```python
>>> db.query((db.Q.first == "George").and_(db.Q.last == "Martin")).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Can do inequalities too


```python
>>> db.query(db.Q.born < 1930).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Queries support: `==`, `!=`, `<`, `<=`, `>`, `>=` for normal comparisons.

In addition they support

- `%` : `LIKE`
- `*` : `GLOB`
- `@` : `REGEXP` using Python's regex module. Note that this is DISABLED by default



```python
>>> # This will all be the same
>>> db.query(db.Q.role % "prod%").all()  # LIKE
>>> db.query(db.Q.role * "prod*").all()  # GLOB
>>> db.query(db.Q.role @ "prod").all()  # REGEXP -- Python based
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



### Sorting / Ordering

JSONLiteDB supports `_orderby` on `query()` and helpers that wrap it, such as `one()` and `count()` (see Advanced Usage).

The input is effectively the same as a query path, but it does not include a value and can use "+" for ascending order (the default) or "-" for descending order. See the help for `query()` for more details, including how ordering works with the different path forms.


```python
>>> db.query(db.Q.first == "George").all()
```




    [{'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]




```python
>>> db.query(db.Q.first == "George", _orderby="-role").all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'},
     {'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'}]




```python
>>> db.query(_orderby=[-db.Q.role, db.Q.last]).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'},
     {'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'John', 'last': 'Lennon', 'born': 1940, 'role': 'guitar'},
     {'first': 'Ringo', 'last': 'Starr', 'born': 1940, 'role': 'drums'},
     {'first': 'Paul', 'last': 'McCartney', 'born': 1942, 'role': 'bass'}]



You can sort by subkeys and subelements as well with a similar syntax to queries. See `query()` for more details.

### Speeding up queries

Queries can be **greatly accelerated** with an index. Note that SQLite is *extremely* picky about how you write the index! For the most part, if you use the same path form for the query and the index, you will be fine. (This is more of an issue with nested queries and *advanced* query formulations.)

The name of the index is immaterial. It is derived from the fields, so it may look different from these examples.


```python
>>> db.create_index("last")
>>> db.indexes
```




    {'ix_items_1bd45eb5': ['$."last"']}



Of course, with four items, this makes little difference but can **greatly accelerate** hot query paths.


```python
>>> list(db.query(last="Martin"))
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



And an index can also be used to enforce uniqueness amongst one or more fields


```python
>>> db.create_index("first", "last", unique=True)
>>> db.indexes
```




    {'ix_items_1bd45eb5': ['$."last"'],
     'ix_items_250e4243_UNIQUE': ['$."first"', '$."last"']}




```python
>>> # db.insert({'first': 'George', 'last': 'Martin', 'type':'FAKE ENTRY'})
>>> # Causes: IntegrityError: UNIQUE constraint failed: index 'ix_items_250e4243_UNIQUE'
```

See *Advanced Usage* for more examples including nested queries and more complex logic.
<!--- END AUTO GENERATED -->

## Queries and Paths

Queries are detailed in the `db.query()` method. All queries and paths can take four basic forms, but query objects are, by far, the most versatile.

<table>  
<thead>  
    <tr>  
        <th>Type</th>  
        <th>Path (e.g. <code>create_index()</code>)</th>  
        <th>Query (e.g. <code>  query()</code>)</th>  
        <th>Comments</th>  
    </tr>  
</thead>  
<tbody>  
    <tr>  
        <td>Plain string</td>  
        <td><code>'itemkey'</code>  
        <td><code>{'itemkey':'query_val'}</code></td>  
        <td>Limited to a single item</td>  
    </tr>  
    <tr>  
        <td>JSON Path string</td>  
        <td>  
            <code>'$.itemkey'</code>  
            <br>  
            <code>'$.itemkey.subkey'</code>  
            <br>  
            <code>'$.itemkey[4]'</code>  
            <br>  
            <code>'$.itemkey.subkey[4]'</code>  
        </td>  
        <td>  
            <code>{'$.itemkey':'query_val'}</code>  
            <br>  
            <code>{'$.itemkey.subkey':'query_val'}</code>  
            <br>  
            <code>{'$.itemkey[4]':'query_val'}</code>  
            <br>  
            <code>{'$.itemkey.subkey[4]':'query_val'}</code>  
        </td>  
        <td>Be careful about indices on JSON path strings. See more below</td>  
    </tr>  
    <tr>  
        <td>Tuples (or lists)</td>  
        <td>  
            <code>('itemkey',)</code>  
            <br>  
            <code>('itemkey','subkey')</code>  
            <br>  
            <code>('itemkey',4)</code>  
            <br>  
            <code>('itemkey','subkey',4)</code>  
        </td>  
        <td>  
            <code>{('itemkey',):'query_val'}</code>  
            <br>  
            <code>{('itemkey','subkey'):'query_val'}</code>  
            <br>  
            <code>{('itemkey',4):'query_val'}</code>  
            <br>  
            <code>{('itemkey','subkey',4):'query_val'}</code>  
        </td>  
        <td></td>  
    </tr>   
    <tr>  
        <td>Query Objects.<br>(Let <code>db</code> be your database)</td>  
        <td>  
            <code>db.Q.itemkey</code>  
            <br>  
            <code>db.Q.itemkey.subkey</code>  
            <br>  
            <code>db.Q.itemkey[4]</code>  
            <br>  
            <code>db.Q.itemkey.subkey[4]</code>  
        </td>  
        <td>  
            <code>db.Q.itemkey == 'query_val'</code>  
            <br>  
            <code>db.Q.itemkey.subkey == 'query_val'</code>  
            <br>  
            <code>db.Q.itemkey[4] == 'query_val'</code>  
            <br>  
            <code>db.Q.itemkey.subkey[4] == 'query_val'</code>  
        </td>  
        <td>  
            See below. Can also do many more types of comparisons beyond equality  
        </td>  
</tbody>  
</table>

Note that JSON Path strings presented here are unquoted, but all other methods will quote them. For example, `'$.itemkey.subkey'` and `('itemkey','subkey')` are *functionally* identical; the latter becomes `'$."itemkey"."subkey"'`. While they are functionally the same, an index created on one will not be used on the other.

### Query Objects

Query Objects provide a great deal more flexibility than other forms.

They can handle normal equality `==` but can handle inequalities, including `!=`, `<`, `<=`, `>`, `>=`.  
    
    db.Q.item < 10  
    db.Q.other_item > 'bla'

They can also handle logic. Note that you must be *very careful* about parentheses.

    (db.Q.item < 10) & (db.Q.other_item > 'bla') # AND  
    (db.Q.item < 10) | (db.Q.other_item > 'bla') # OR  
    
or

    (db.Q.item < 10).and_(db.Q.other_item > 'bla') # AND  
    (db.Q.item < 10).or_(db.Q.other_item > 'bla')  # OR  
    
Note that while something like `10 <= var <= 20` is valid Python, a query must be done like:

    (10 <= db.Q.var) & (db.Q.var <= 20)
    (10 <= db.Q.var).and_(db.Q.var <= 20)

And, as noted in "Basic Usage," they can do SQL `LIKE` comparisons (`db.Q.key % "%Val%"`), `GLOB` comparisons (`db.Q.key * "file*.txt"`), and opt-in `REGEXP` comparisons (`db.Q.key @ "\S+?\.[A-Z]"`).  

### REGEXP Opt-In

`REGEXP` (the `@` query operator) uses Python's `re` engine and may be unsafe for untrusted patterns. It is therefore disabled by default.

To enable it, set the environment variable before importing/creating a database:

```bash
export JSONLITEDB_ENABLE_REGEX=1
```

You can also enable it in code (for new queries and new connections) after import:

```python
import jsonlitedb
jsonlitedb.ENABLE_REGEX = True
```

If you need to force it off, the legacy disable flag still overrides opt-in:

```bash
export JSONLITEDB_DISABLE_REGEX=1
```

```python
import jsonlitedb
jsonlitedb.DISABLE_REGEX = True
```

When disabled, attempting to build a `REGEXP` query raises an error before SQL is sent to SQLite. This is intentional so the behavior does not depend on whether the underlying SQLite build happens to provide a `REGEXP` function.
  
#### Form

You can mix and match index or attribute for keys. The following are all **identical**:

- `db.Q.itemkey.subkey`  
- `db.Q['itemkey'].subkey`  
- `db.Q['itemkey','subkey']`  
- `db.Q['itemkey']['subkey']`  
- ...

## Command Line Tools

JSONLiteDB also installs a tool called "jsonlitedb" that makes it easy to read JSONL and JSON files into a database. This is useful for converting existing databases or appending data. The same workflow is available in the API via `db.import_jsonl(...)` and `db.export_jsonl(...)`.

`insert` and `import` are the same command behavior for file/stdin input.
`insert` keeps legacy positional file support for compatibility; `import` is
the preferred form for positional file input. `add` is shorthand for `insert --json` and treats
its positional `JSON_ITEM` arguments as `--json JSON_ITEM`.

For CLI usage only, you can set `JSONLITEDB_CLI_TABLE` to change the default table name.  
Passing `--table` on a command overrides the environment variable.

    $ jsonlitedb insert mydb.db newfile.jsonl  
    $ jsonlitedb import mydb.db newfile.jsonl  
    $ cat newdata.jsonl | jsonlitedb insert mydb.db  
    $ jsonlitedb add mydb.db '{"name":"new item","ii":42}'
    
It can also dump a database to JSONL.

    $ jsonlitedb dump mydb.db    # stdout  
    $ jsonlitedb dump mydb.db --output db.jsonl

## Known Limitations

- Dictionary keys must be strings without a dot, double quote, square bracket, and may not start with `_`, `+`, or `-`. Some of these may work but could have unexpected and untested consequences.
- Functionally identical queries may not match for an index because SQLite is *extremely strict* about the pattern. Mitigate by using the same query mechanics for index creation and query. 
- Equality-style `None` queries do not distinguish between a key set to `None` and a missing key. Use `db.Q.path.exists_()` and `db.Q.path.missing_()` with `query()` or `count()` when you need to test path existence; these predicates can be composed with other query conditions.
- While it will accept non-dict items like strings, lists, and tuples as a single item, queries on these do not work reliably.

## Vendoring

The core library is intentionally self-contained in `jsonlitedb/jsonlitedb.py`, so vendoring the database implementation into another project is straightforward.

If you do that, note that the packaged distribution also includes separate `__init__.py` and CLI support.


## Similar tools and inspiration

Many ideas were borrowed but they all have different tradeoffs. JSONLiteDB's API is somewhat close to TinyDB and the storage is close to KenobiDB. Dataset has the closest *vibe* but doesn't handle a mix of keys (and with an index, the speed is about the same). DictTable is entirely in memory and uses Python dicts (hash table) instead of B-Trees.

- [TinyDB](https://github.com/msiemens/tinydb). The API and process of TinyDB heavily inspired JSONLiteDB. But TinyDB reads the entire JSON DB into memory and needs to dump the entire database upon insertion. Hardly efficient or scalable and still queries at O(N).
- [Dataset](https://github.com/pudo/dataset) is promising but creates new columns for every key and is very "heavy" with its dependencies. As far as I can tell, there is no native way to support multi-column and/or unique indexes. But still, a very promising tool!
- [KenobiDB](https://github.com/patx/kenobi). Came out while JSONLiteDB was in development. Similar idea with different design decisions. Does not directly support advanced queries indexes which can *greatly* accelerate queries! (Please correct me if I am wrong. I new to this tool)
- [DictTable](https://github.com/Jwink3101/dicttable) (also written by me) is nice but entirely in-memory and not always efficient for non-equality queries.

## FAQs

### Wouldn't it be better to use different SQL columns rather than all as JSON?

Yes and no. The idea is the complete lack of schema needed and as a notable improvement to a JSON file. Plus, if you index the field of interest, you get super-fast queries all the same! If this is an important feature, check out [Dataset](https://github.com/pudo/dataset).

### Aren't there other embedded object databases that are purpose built rather than on top of SQLite?

Yes! The idea is simplicity and compatibility. SQLite basically runs everywhere and is widely accepted. It is only a slight step down from JSON Lines in being future proof. 

There really aren't any other single-file, embedded \[JSON\] object storage databases with anywhere near the ubiquity or pedigree of SQLite.

### When using `duplicates='replace'`, it essentially deletes and inserts the item rather than replacing it for real (and keeping the `rowid` internally). Is that intended?

Mostly yes. The alternative was considered but this behavior more closely matches the mental model of the tool.

### What if I need more advanced manipulation?

JSONLiteDB provides a lot of functionality between queries and sorting but if you need more, just run on the database directly yourself!

Similarly, the minimal CLI can help in some cases but JSONLiteDB is really meant to be accessed as a library.

### I created an index but when I test with `explain_query()`, it isn't being used.

Chances are you have an index on something that is *functionally* correct but still different and therefore unrecognized by SQLite. For example: `'$.itemkey.subkey[4]'` and `('itemkey','subkey',4)` are functionally identical but will not use the same index. The latter resolves to `'$."itemkey"."subkey"[4]'`

### Can I use a custom encoder?

Yes and no. You can use your own methods to encode the object you insert but since it uses SQLite's `JSON1`, it must be JSON that gets stored. You could probably hack something else into it but it is not recommended.

### When Should or Shouldn't I Use JSONLiteDB?

JSONLiteDB is useful when you want to store JSON-like Python dictionaries without designing a full relational schema, but still want SQLite durability, querying, sorting, and indexes. It is also good when you do not want to have to write the entire file for every update or delete. It fits small to medium local databases, scripts, CLI tools, cached API responses, lightweight app state, and workflows where records may not all share the same shape.

It is usually not the right tool for heavily relational data, complex joins, high-write-concurrency systems, strict schemas with migrations, or large analytical workloads. In those cases, use SQLite directly with normalized tables, another relational database, or a document database designed for that scale.

### Why is REGEXP disabled by default?

REGEXP queries (`@`) rely on Python's `re` module, which can suffer from ReDoS (regular expression denial of service) through catastrophic backtracking. This does *not* pose a data exfiltration risk, but an expensive pattern can degrade performance or tie up the process.

Because REGEXP is evaluated in Python, it is also slower than SQLite's `GLOB` (`*`) or `LIKE` (`%`) operators. Those SQLite operators are faster in general and can sometimes use an index, depending on the index and query shape.

## AI/LLM/Agent Disclosure

*We do not reject the use of AI-, LLM-, or agent-driven development, including “vibe coding.” However, we believe it is important to provide appropriate disclosure, as outlined below. We also prefer human-verified code and place high value on the trust users place in this project.*

Up until version 0.1.10, there was no use of coding agents and only minimal AI via a chat interface. After that, OpenAI Codex was used to make small changes or perform grunt work. It also helped identify and fix (minor) security gaps. 

These changes were all done minimally and with close human review. There was no black-box "vibe-coding" and this largely remains a human-developed tool.

Beginning in 0.3.0, something closer to "vibe-coding" was used to expand the CLI surface and refactor into files. It was still reviewed and the majority of the critical module remains primarily human-written.

---
<!-- From https://github.com/dwyl/repo-badges -->  
[100%]:https://img.shields.io/codecov/c/github/dwyl/hapi-auth-jwt2.svg
