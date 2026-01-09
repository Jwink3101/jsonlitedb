# JSONLiteDB

SQLite3-backed JSON document database with support for indices and advanced queries.

<img src="logo.svg" alt="Logo" height="250" />

![100% Coverage][100%]

## Premise and Inspiration

JSONLiteDB leverages [SQLite3](https://sqlite.org/index.html) and [JSON1](https://sqlite.org/json1.html) to create a fast JSON document store with easy persistence, indexing capability, and extensible use.

JSONLiteDB provides an easy API with no need to load the entire database into memory, nor dump it when inserting! JSONLiteDB SQLite files are easily usable in other tools with no proprietary formats or encoding. JSONLiteDB is a great replacement for reading a JSON or JSONLines file. Entries can be modified in place. Queries can be indexed for *greatly* improved query speed and optionally to enforce uniqueness.

Similar tools and inspiration:

- [TinyDB](https://github.com/msiemens/tinydb). The API and process of TinyDB heavily inspired JSONLiteDB. But TinyDB reads the entire JSON DB into memory and needs to dump the entire database upon insertion. Hardly efficient or scalable and still queries at O(N).
- [Dataset](https://github.com/pudo/dataset) is promising but creates new columns for every key and is very "heavy" with its dependencies. As far as I can tell, there is no native way to support multi-column and/or unique indexes. But still, a very promising tool!
- [KenobiDB](https://github.com/patx/kenobi). Came out while JSONLiteDB was in development. Similar idea with different design decisions. Does not directly support advanced queries indexes which can *greatly* accelerate queries! (Please correct me if I am wrong. I new to this tool)
- [DictTable](https://github.com/Jwink3101/dicttable) (also written by me) is nice but entirely in-memory and not always efficient for non-equality queries.

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
>>> from jsonlitedb import JSONLiteDB
```


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

Let's do some simple queries. The default `query()` returns an iterator so we wrap them in a list.


```python
>>> db.query(first="George").all()
```




    [{'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]




```python
>>> # If you only one the first result, you can use db.one().
>>> # On the SQL call, this adds "LIMIT 1"
>>> db.one(first="George", last="Martin")
```




    {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}




```python
>>> # This will also only give you the first row but it is
>>> # less efficient as it doesn't have a "LIMIT 1" clause.
>>> db.query(first="George", last="Martin").one()
```




    {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}



Now let's query with a dictionary to match


```python
>>> # queries return a QueryResult which can be iterated. list(QueryResult) <==> QueryResult.all()
>>> list(db.query({"first": "George"}))
```




    [{'first': 'George', 'last': 'Harrison', 'born': 1943, 'role': 'guitar'},
     {'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Multiples are always an AND query


```python
>>> db.query({"first": "George", "last": "Martin"}).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Can do seperate items but it makes no difference.


```python
>>> db.query({"first": "George"}, {"last": "Martin"}).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]




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



Note that you need to be careful with parentheses as the operator precedance for the `&` and `|` are very high


```python
>>> db.query((db.Q.first == "George") & (db.Q.last == "Martin")).all()
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Can do inequalities too


```python
>>> list(db.query(db.Q.born < 1930))
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



Queries support: `==`, `!=`, `<`, `<=`, `>`, `>=` for normal comparisons.

In addition they support

- `%` : `LIKE`
- `*` : `GLOB`
- `@` : `REGEXP` using Python's regex module



```python
>>> # This will all be the same
>>> db.query(db.Q.role % "prod%").all()  # LIKE
>>> db.query(db.Q.role * "prod*").all()  # GLOB
>>> db.query(db.Q.role @ "prod").all()  # REGEXP -- Python based
```




    [{'first': 'George', 'last': 'Martin', 'born': 1926, 'role': 'producer'}]



### Sorting / Ordering

JSONLiteDB supports `_orderby` on `query()` (and those that wrap it) and `query_by_path_exists()` (see Advanced Usage)

The input is effectively the same as those for a query but (a) do not have values assigned and (b) can take "+" (ascending,default) or "-" (descending) construction. See the help for `query()` for more details including how it is used with the different forms


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

Queries can be **greatly accelerated** with an index. Note that SQLite is *extremely* picky about how you write the index! For the most part, if you the same method to query as write the index, you will be fine. (This is more of an issue with nested queries and *advanced* formulating of the query).

The name of the index is imaterial. It is based on the fields. It will look different


```python
>>> db.create_index("last")
>>> db.indexes
```




    {'ix_items_1bd45eb5': ['$."last"']}




```python
>>> # of course, with four items, this makes little difference
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

See *Advanced Usage* for more examples including nested queries


```python
>>> 
```
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
    
Note that while something like `10 <= var <= 20` is valid Python, a query must be done like:

    (10 <= db.Q.var) & (db.Q.var <= 20 )

And, as noted in "Basic Usage," they can do SQL `LIKE` comparisons (`db.Q.key % "%Val%"`), `GLOB` comparisons (`db.Q.key * "file*.txt"`), and `REGEXP` comparisons (`db.Q.key @ "\S+?\.[A-Z]"`).  
  
#### Form

You can mix and match index or attribute for keys. The following are all **identical**:

- `db.Q.itemkey.subkey`  
- `db.Q['itemkey'].subkey`  
- `db.Q['itemkey','subkey']`  
- `db.Q['itemkey']['subkey']`  
- ...

## Command Line Tools

JSONLiteDB also installs a tool called "jsonlitedb" that makes it easy to read JSONL and JSON files into a database. This is useful for converting existing databases or appending data.

    $ jsonlitedb insert mydb.db newfile.jsonl  
    $ cat newdata.jsonl | jsonlitedb insert mydb.db  
    
It can also dump a database to JSONL.

    $ jsonlitedb dump mydb.db    # stdout  
    $ jsonlitedb dump mydb.db --output db.jsonl

## Known Limitations

- Dictionary keys must be strings without a dot, double quote, square bracket, and may not start with `_`. Some of these may work but could have unexpected outcomes.
- Functionally identical queries may not match for an index because SQLite is *extremely strict* about the pattern. Mitigate by using the same query mechanics for index creation and query. 
- There is no distinction made between an entry having a key with a value of `None` vs. not having the key. However, you can use `query_by_path_exists()` to query items that have a certain path. There is no way still to mix this with other queries testing existence other than with `None`.  
- While it will accept non-dict items like strings, lists, and tuples as a single item, queries on these do not work reliably.

## FAQs

### Wouldn't it be better to use different SQL columns rather than all as JSON?

Yes and no. The idea is the complete lack of schema needed and as a notable improvement to a JSON file. Plus, if you index the field of interest, you get super-fast queries all the same!

### Aren't there other embedded object databases that are purpose built rather than on top of SQLite?

Yes! The idea is simplicity and compatibility. SQLite basically runs everywhere and is widely accepted. It is only a slight step down from JSON Lines in being future proof. 

### When using `duplicates='replace'`, it essentially deletes and inserts the item rather than replacing it for real (and keeping the `rowid` internally). Is that intended?

Mostly yes. The alternative was considered but this behavior more closely matches the mental model of the tool.

### What if I need more advanced manipulation?

JSONLiteDB provides a lot of functionality between queries and sorting but if you need more, just run on the database directly yourself!

### Can I use a custom encoder?

Yes and no. You can use your own methods to encode the object you insert but since it uses SQLite's `JSON1`, it must be JSON that gets stored.

<!-- From https://github.com/dwyl/repo-badges -->  
[100%]:https://img.shields.io/codecov/c/github/dwyl/hapi-auth-jwt2.svg
