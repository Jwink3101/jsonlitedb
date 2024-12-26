# API Documentation

Auto-generated documentation

## JSONLiteDB

```text
Help on class JSONLiteDB in jsonlitedb:

jsonlitedb.JSONLiteDB = class JSONLiteDB(builtins.object)
 |  jsonlitedb.JSONLiteDB(dbpath, table='items', **sqlitekws)
 |  
 |  JSON(Lines) SQLite Database. Simple SQLite3 backed JSON-based document database
 |  
 |  Inputs:
 |  -------
 |  dbpath
 |      String path representing the database. Can also be ':memory:'. If uri=True
 |      is passed, can be an SQLite URI path (including read-only flags)
 |  
 |  table [DEFAULT_TABLE == 'items']
 |      Table name
 |  
 |  **sqlitekws
 |      Passed to sqlite3.connect. Some useful examples:
 |          check_same_thread, uri
 |  
 |  Methods defined here:
 |  
 |  AVG = _method(self, path, /, *, function='AVG')
 |  
 |  COUNT = _method(self, path, /, *, function='COUNT')
 |  
 |  MAX = _method(self, path, /, *, function='MAX')
 |  
 |  MIN = _method(self, path, /, *, function='MIN')
 |  
 |  SUM = _method(self, path, /, *, function='SUM')
 |  
 |  TOTAL = _method(self, path, /, *, function='TOTAL')
 |  
 |  __call__ = query(self, *query_args, **query_kwargs)
 |  
 |  __del__ = close(self)
 |  
 |  __delitem__(self, rowid)
 |  
 |  __enter__(self)
 |      # These methods let you call the db as a context manager to do multiple transactions
 |      # but only commits if it is the last one. All internal methods call this one so as to
 |      # no commit before transactions are finished
 |  
 |  __exit__(self, exc_type, exc_val, exc_tb)
 |  
 |  __getitem__(self, rowid)
 |  
 |  __init__(self, /, dbpath, table='items', **sqlitekws)
 |      Initialize self.  See help(type(self)) for accurate signature.
 |  
 |  __iter__ = items(self, _load=True)
 |  
 |  __len__(self)
 |  
 |  __repr__(self)
 |      Return repr(self).
 |  
 |  __str__ = __repr__(self)
 |  
 |  add = insert(self, *items, duplicates=False, _dump=True)
 |  
 |  aggregate(self, path, /, function)
 |      Compute the aggregate of a given path/key.
 |      
 |      Valid functions are:
 |          avg, count, max, min, sum, total
 |      
 |      See https://www.sqlite.org/lang_aggfunc.html for description
 |  
 |  close(self)
 |  
 |  count(self, *query_args, **query_kwargs)
 |      Return the number of items that match the query
 |      rather than the items. See query() for details
 |  
 |  create_index(self, *paths, unique=False)
 |      Create an index. Indices can *dramatically* accelerate queries so use them
 |      if often querying some result.
 |      
 |      Note that order *does* matter when using multiple keys/paths. The order will be
 |      in order of arguments then order of keywords.
 |      
 |      Inputs:
 |      -------
 |      *paths
 |          Strings (either a single key or a JSON path), tuple, or query object.
 |          Query objects must *not* have values assigned to them (e.g. 'db.Q.key' is
 |          acceptable but 'db.Q.key == val' will fail).
 |      
 |      unique [False]
 |          Add a "UNIQUE" constraint to the index.
 |      
 |      Examples:
 |      ---------
 |          db.create_index('key1')                   # Single Key
 |          db.create_index('key1','key2')            # Multiple keys
 |      
 |          db.create_index(('key1','subkey'))        # Path with subkeys
 |          db.create_index(db.Q.onekey.twokey[3])    # Path w/ list index
 |          db.create_index(('onekey','twokey',3))    # Equiv to above
 |      
 |          db.create_index(db.Q.key1,db.Q.key2.subkey, db.Q.key3[4])
 |                                                    # Multiple advanced queries
 |      Note:
 |      -----
 |      sqlite3 is EXTREMELY sensitive to the form of the query. For example:
 |      db.create_index('key') and db.create_index('$.key'), which are identical,
 |      will not use the same index. (This is because the former becomes '$."key"'
 |      which is not the same as '$.key').
 |  
 |  delete = remove(self, *query_args, **query_kwargs)
 |  
 |  delete_by_rowid = remove_by_rowid(self, *rowids)
 |  
 |  drop_index(self, *paths, unique=False)
 |      Delete an by query. Must match exactly as used to build index including
 |      unique settings
 |  
 |  drop_index_by_name(self, name)
 |      Delete an index by name. The names can be found with the db.indexes attribute
 |  
 |  get_by_rowid(self, rowid, *, _load=True)
 |      Get row by rowid. Can only specify one
 |  
 |  insert(self, *items, duplicates=False, _dump=True)
 |      Insert one or more items where each item is an argument.
 |      
 |      *items
 |          items to add. Each item is its own argument. Otherwise, see
 |          insertmany()
 |      
 |      duplicates [False] -- Options: False, True, "ignore", "replace"
 |          How to handle duplicate items IF AND ONLY IF there is a "unique" index.
 |          If there isn't a unique index, items will be added regardless!
 |              False     : Do nothing but a unique index will cause an error
 |              True      : Same as "replace"
 |              "replace" : Replace items that violate a unique index
 |              "ignore"  : ignore items that violate a unique index
 |      
 |      _dump [True]
 |          Converts items to JSON. Set to False if input is already JSON.
 |      
 |      See also: insertmany
 |  
 |  insertmany(self, items, duplicates=False, _dump=True)
 |      Insert a list of items. See insert() for help
 |  
 |  items(self, _load=True)
 |      Return an iterator over all items. Order is likely insertion order but should not
 |      be relied upon
 |  
 |  one = query_one(self, *query_args, **query_kwargs)
 |  
 |  path_counts(self, start=None)
 |      Return a dictionary of all paths and number of items, optionally below
 |      "start" (default None).
 |      
 |      Inputs:
 |      ------
 |      start
 |          Starting path for all keys. Default is None which means it gives all paths
 |          at the root.
 |      
 |          Can be string (with '$' for a full path or just a single key without),
 |          a tuple/list, or a Query() object
 |  
 |  query(self, *query_args, **query_kwargs)
 |      Query the database.
 |      
 |      Queries can take some of the following forms:
 |        Keyword:
 |          db.query(key=val)
 |          db.query(key1=val1,key2=val2) # AND
 |      
 |        Arguments:
 |          db.query({'key':val})
 |          db.query({'key1':val1,'key2':val2}) # AND
 |          db.query({'key1':val1,},{'key2':val2}) # AND (as different args)
 |      
 |      Nested queries can be accomplished with arguments. The key can take
 |      the following forms:
 |          - String starting with "$" and follows SQLite's JSON path. Must properly quote
 |            if it has dots, etc. No additional quoting is performed
 |      
 |              Example: {"$.key":'val'}            # Single key
 |                       {"$.key.subkey":'val'}     # Nested keys
 |                       {"$.key.subkey[3]":'val'}  # Nested keys to nested list.
 |      
 |          - Tuple string-keys or integer items. The quoteing will be handled for you!
 |      
 |              Example: {('key',): 'val'}
 |                       {('key','subkey'): 'val'}
 |                       {('key','subkey',3): 'val'}
 |      
 |          - Advaced queries (explained below)
 |      
 |      Advanced queries allow for more comparisons. Note: You must be careful
 |      about parentheses for operations. Keys are assigned with attributes (dot)
 |      and/or items (brackets). Items can have multiple comma-separated ones and
 |      can include integers for searching within a list.
 |      
 |        Example: db.query(db.Q.key == val)
 |                 db.query(db.Q['key'] == val)
 |      
 |                 db.query(db.Q.key.subkey == val)
 |                 db.query(db.Q['key'].subkey == val)
 |                 db.query(db.Q.key.['subkey'] == val)
 |                 db.query(db.Q['key','subkey'] == val)
 |      
 |                 qb.query(db.Q.key.subkey[3] == val)
 |      
 |        Complex Example:
 |          db.query((db.Q['other key',9] >= 4) & (Q().key < 3)) # inequality
 |      
 |      Queries support most comparison operations (==, !=, >,>=,<, <=, etc) plus:
 |          LIKE statements:  db.Q.key % "pat%tern"
 |          GLOB statements:  db.Q.key * "glob*pattern"
 |          REGEX statements: db.Q.key @ "regular.*expressions"
 |      
 |      db.query() is also aliased to db() and db.search()
 |      
 |      Inputs:
 |      ------
 |      *query_args:
 |          Arguments that are either dictionaries of equality key:value, or
 |          advanced queries
 |      
 |      **query_kwargs
 |          Keywords that are equality as explaied above
 |      
 |      _load [True]
 |          Whether or not to load the dict from JSON. Usually what is desired
 |          but may be useful if converting from sqlite3 to jsonl. Note that if not
 |          loaded, the result will not have rowid
 |      
 |      Returns:
 |      -------
 |      QueryResult -- An iterator of DBDicts. DBDicts are dicts with the 'rowid' attribute
 |                                 also specified
 |  
 |  query_by_path_exists(self, path, _load=True)
 |      Return items iterator over items whos path exist. Paths can be nested
 |      and take the usual possible four forms (single-key string, SQLite
 |      JSON path, tuple, query object).
 |      
 |      Note that this is similar to
 |      
 |          >>> db.query(db.Q.path != None)
 |      
 |      but if you have items that are set as `None`, that query will miss it.
 |      
 |      Returns:
 |      -------
 |      QueryResult -- An iterator of DBDicts. DBDicts are dicts with the 'rowid' attribute
 |                                 also specified
 |  
 |  query_one(self, *query_args, **query_kwargs)
 |      Return a single item from a query. See "query" for more details.
 |      
 |      Returns None if nothing matches
 |      
 |      db.query_one() is also aliased to db.one() and db.search_one()
 |  
 |  remove(self, *query_args, **query_kwargs)
 |      Remove all items matching the input. See query() for how to
 |      query
 |  
 |  remove_by_rowid(self, *rowids)
 |      Remove row by rowid. Can specify multiple for improved performance
 |  
 |  search = query(self, *query_args, **query_kwargs)
 |  
 |  search_one = query_one(self, *query_args, **query_kwargs)
 |  
 |  update(self, item, rowid=None, duplicates=False, _dump=True)
 |      Update an entry with 'item'.
 |      
 |      Inputs:
 |      -------
 |      item
 |          Item to update. If 'item' has the attribute 'rowid',
 |          it will be inferred.
 |      
 |      rowid [None]
 |          Rowid of item. If not specified, will try to infer it from
 |          item's rowid attribute. Will raise a MissingRowIDError if it
 |          cannot infer it
 |      
 |      duplicates [False] -- Options: False, True, "ignore", "replace"
 |          How to handle duplicate items IF AND ONLY IF there is a "unique" index.
 |          If there isn't a unique index, items will be added regardless!
 |              False     : Do nothing but a unique index will cause an error
 |              True      : Same as "replace"
 |              "replace" : Replace items that violate a unique index
 |              "ignore"  : ignore items that violate a unique index
 |      
 |      _dump [True]
 |          Converts items to JSON. Set to False if input is already JSON.
 |  
 |  ----------------------------------------------------------------------
 |  Class methods defined here:
 |  
 |  connect(*args, **kwargs) from builtins.type
 |      Shortcut for new. Same as __init__
 |  
 |  open = connect(*args, **kwargs) from builtins.type
 |      Shortcut for new. Same as __init__
 |  
 |  read_only(dbpath, **kwargs) from builtins.type
 |      Shortcut For
 |          JSONLiteDB(f"file:{dbpath}?mode=ro",uri=True,**kwargs)
 |      where **kwargs can contain both JSONLiteDB and sqlite3 args
 |  
 |  ----------------------------------------------------------------------
 |  Readonly properties defined here:
 |  
 |  Q
 |  
 |  Query
 |  
 |  indexes
 |  
 |  indices
 |  
 |  ----------------------------------------------------------------------
 |  Data descriptors defined here:
 |  
 |  __dict__
 |      dictionary for instance variables (if defined)
 |  
 |  __weakref__
 |      list of weak references to the object (if defined)

```

## Query

```text
Help on class Query in jsonlitedb:

jsonlitedb.Query = class Query(builtins.object)
 |  Query object to allow for more complex queries.
 |  
 |  Methods defined here:
 |  
 |  __add__(self, item)
 |  
 |  __and__ = _method(self, other, *, comb='AND')
 |  
 |  __call__(self)
 |      Enable it to be called. Lessens mistakes when used as property of db
 |  
 |  __eq__ = _method(self, val, *, sym='=')
 |  
 |  __ge__ = _method(self, val, *, sym='>=')
 |  
 |  __getattr__(self, attr)
 |      ## Key Builders
 |  
 |  __getitem__(self, item)
 |  
 |  __gt__ = _method(self, val, *, sym='>')
 |  
 |  __init__(self)
 |      Initialize self.  See help(type(self)) for accurate signature.
 |  
 |  __invert__(self)
 |  
 |  __le__ = _method(self, val, *, sym='<=')
 |  
 |  __lt__ = _method(self, val, *, sym='<')
 |  
 |  __matmul__ = _method(self, val, *, sym='REGEXP')
 |  
 |  __mod__ = _method(self, val, *, sym='LIKE')
 |  
 |  __mul__ = _method(self, val, *, sym='GLOB')
 |  
 |  __ne__ = _method(self, val, *, sym='!=')
 |  
 |  __or__ = _method(self, other, *, comb='OR')
 |  
 |  __repr__ = __str__(self)
 |  
 |  __setattr__(self, attr, val)
 |      Implement setattr(self, name, value).
 |  
 |  __setitem__(self, attr, item)
 |  
 |  __str__(self)
 |      Return str(self).
 |  
 |  ----------------------------------------------------------------------
 |  Data descriptors defined here:
 |  
 |  __dict__
 |      dictionary for instance variables (if defined)
 |  
 |  __weakref__
 |      list of weak references to the object (if defined)
 |  
 |  ----------------------------------------------------------------------
 |  Data and other attributes defined here:
 |  
 |  __hash__ = None

```