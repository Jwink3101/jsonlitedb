# API Documentation

Auto-generated documentation

## JSONLiteDB

```text
Help on class JSONLiteDB in jsonlitedb:

jsonlitedb.JSONLiteDB = class JSONLiteDB(builtins.object)
 |  jsonlitedb.JSONLiteDB(dbpath, table='items', **sqlitekws)
 |
 |  JSON(Lines) SQLite Database. Simple SQLite3 backed JSON-based document database
 |  with powerful queries and indexing.
 |
 |  Initialize a JSONLiteDB instance.
 |
 |  Parameters:
 |  -----------
 |  dbpath : str
 |      Path to the SQLite database file. Use ':memory:' for an in-memory database.
 |  table : str, optional
 |      Name of the database table to use. Defaults to 'items'.
 |  **sqlitekws : keyword arguments
 |      Additional keyword arguments passed to sqlite3.connect. See [1] for
 |      more details.
 |
 |  Raises:
 |  -------
 |  sqlite3.Error
 |      If there is an error connecting to the database.
 |  Examples:
 |  ---------
 |  >>> db = JSONLiteDB(':memory:')
 |  >>> db = JSONLiteDB('my/database.db',table='Beatles')
 |  >>> db = JSONLiteDB('data.db',check_same_thread=False)
 |
 |
 |  References:
 |  -----------
 |  [1] https://docs.python.org/3/library/sqlite3.html#module-functions
 |
 |  Methods defined here:
 |
 |  AVG = _method(self, path, /, *, function='AVG') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  COUNT = _method(self, path, /, *, function='COUNT') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  MAX = _method(self, path, /, *, function='MAX') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  MIN = _method(self, path, /, *, function='MIN') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  SUM = _method(self, path, /, *, function='SUM') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  TOTAL = _method(self, path, /, *, function='TOTAL') from functools.partialmethod._make_unbound_method.<locals>
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
 |      Return the number of items in the database.
 |
 |      Returns:
 |      --------
 |      int
 |          The total number of JSON objects stored in the database.
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insert({'first': 'John', 'last': 'Lennon'})
 |      >>> db.insert({'first': 'Paul', 'last': 'McCartney'})
 |      >>> print(len(db))
 |      2
 |
 |      This example shows how to use `len()` to get the count of items in the database.
 |
 |  __repr__(self)
 |      Return repr(self).
 |
 |  __str__ = __repr__(self)
 |
 |  add = insert(self, *items, duplicates=False, _dump=True)
 |
 |  aggregate(self, path, /, function)
 |      Compute an aggregate function over a specified JSON path.
 |
 |      Parameters:
 |      -----------
 |      path : str or tuple
 |          The JSON path to aggregate. Can be a string or tuple representing the path.
 |
 |      function : str
 |          The aggregate function to apply. Options are 'AVG', 'COUNT', 'MAX', 'MIN',
 |          'SUM', or 'TOTAL'.
 |
 |      Returns:
 |      --------
 |      float or int
 |          The result of the aggregate function applied to the specified path.
 |
 |      Raises:
 |      -------
 |      ValueError
 |          If an unallowed aggregate function is specified.
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insertmany([{'value': 10}, {'value': 20}, {'value': 30}])
 |      >>> avg_value = db.aggregate('value', 'AVG')
 |      >>> print(avg_value)
 |      20.0
 |
 |      OR
 |
 |      >>> db.AVG('value') # 20.0 Same as above
 |
 |      This example calculates the average of the 'value' field across all items.
 |
 |  close(self)
 |      Close the database connection.
 |
 |      This method should be called when the database is no longer needed to
 |      ensure that all resources are properly released.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.close()
 |
 |      This example demonstrates closing the database connection when done.
 |
 |  count(self, *query_args, **query_kwargs)
 |      Count the number of items matching the query criteria.
 |
 |      Parameters:
 |      -----------
 |      *query_args : positional arguments
 |          Arguments can be dictionaries of equality key:value pairs or advanced
 |          queries. Multiple are combined with AND logic. See query() for details.
 |
 |      **query_kwargs : keyword arguments
 |          Keywords that represent equality conditions. Multiple are combined with
 |          AND logic.
 |
 |      Returns:
 |      --------
 |      int
 |          The number of items matching the query criteria.
 |
 |      Examples:
 |      ---------
 |      >>> db.count(first='George')
 |
 |  create_index(self, *paths, unique=False)
 |      Create an index on specified JSON paths to improve query performance.
 |
 |      Parameters:
 |      -----------
 |      *paths : variable length argument list
 |          Paths to index. Can be strings, tuples, or query objects.
 |
 |      unique : bool, optional
 |          If True, creates a unique index. Defaults to False.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Examples:
 |      ---------
 |      >>> db.create_index('first')                # Single Key
 |
 |      >>> db.create_index('first','last')         # Multiple keys
 |      >>> db.create_index(db.Q.first,db.Q.last)   # Multiple advanced queries
 |
 |      >>> db.create_index(('address','city'))     # Path with subkeys
 |      >>> db.create_index(db.Q.addresses[1])      # Path w/ list index
 |      >>> db.create_index(('addresses',3))        # Equiv to above
 |
 |      Note:
 |      -----
 |      sqlite3 is EXTREMELY sensitive to the form of the query. For example:
 |      db.create_index('key') and db.create_index('$.key'), which are identical in
 |      practice, will not use the same index. (This is because the former becomes
 |      '$."key"' which is not the same as '$.key').
 |
 |      It is best to always use the same construction as query() to be certain.
 |
 |  delete = remove(self, *query_args, **query_kwargs)
 |
 |  delete_by_rowid = remove_by_rowid(self, *rowids)
 |
 |  drop_index(self, *paths, unique=False)
 |      Delete an index from the database by query paths.
 |
 |      Parameters:
 |      -----------
 |      *paths : variable length argument list
 |          Paths for which the index was created. Can be strings, tuples, or query objects.
 |
 |      unique : bool, optional
 |          Indicates whether the index was created as unique. Defaults to False.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.create_index('first', 'last', unique=True)
 |      >>> print(db.indexes)
 |      {'ix_items_250e4243_UNIQUE': ['$."first"', '$."last"']}
 |      >>> db.drop_index('first', 'last') # Does nothing. Not the same index
 |      >>> print(db.indexes)
 |      {'ix_items_250e4243_UNIQUE': ['$."first"', '$."last"']}
 |      >>> db.drop_index('first', 'last', unique=True)
 |      >>> print(db.indexes)
 |      {}
 |
 |      This example creates a UNIQUE index on the 'first' and 'last' field, then shows
 |      that dropping it w/o unique=True fails to do so but works as expected when
 |      specified.
 |
 |  drop_index_by_name(self, name)
 |      Delete an index from the database by its name.
 |
 |      Parameters:
 |      -----------
 |      name : str
 |          The name of the index to be dropped.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.create_index('first', 'last')
 |      >>> print(db.indexes)
 |      {'ix_items_250e4243': ['$."first"', '$."last"']}
 |      >>> db.drop_index_by_name('ix_items_250e4243')
 |      >>> print(db.indexes)
 |      {}
 |
 |      This example creates an index on the 'first' and 'last' field, then drops it
 |      using its name.
 |
 |  get_by_rowid(self, rowid, *, _load=True)
 |      Retrieve an item from the database by its rowid.
 |
 |      Parameters:
 |      -----------
 |      rowid : int
 |          The rowid of the item to retrieve.
 |
 |      _load : bool, optional
 |          Determines whether to load the result as a JSON object. Defaults to True.
 |
 |      Returns:
 |      --------
 |      DBDict or None
 |          The item as a DBDict if found, or None if no item exists with the specified rowid.
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insert({'first': 'George', 'last': 'Martin', 'birthdate': 1926})
 |      >>> item = db.query_one(first='George', last='Martin')
 |      >>> retrieved_item = db.get_by_rowid(item.rowid)
 |      >>> print(retrieved_item)
 |      {'first': 'George', 'last': 'Martin', 'birthdate': 1926}
 |
 |      This example demonstrates retrieving an item using its rowid.
 |
 |  insert(self, *items, duplicates=False, _dump=True)
 |      Insert one or more JSON items into the database.
 |
 |      Parameters:
 |      -----------
 |      *items : variable length argument list
 |          Items to add to the database. Each item should be a dictionary representing
 |          a JSON object.
 |
 |      duplicates : bool or str, optional
 |          Specifies how to handle duplicate items if a unique index exists.
 |          Options are:
 |          - False (default): Raises an error if a duplicate is found.
 |          - True or "replace": Replaces existing items that violate a unique index.
 |          - "ignore": Ignores items that violate a unique index.
 |
 |      _dump : bool, optional
 |          If True (default), converts items to JSON strings before insertion.
 |          Set to False if the input is already a JSON string.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Raises:
 |      -------
 |      ValueError
 |          If `duplicates` is not one of {True, False, "replace", "ignore"}.
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insert({'first': 'John', 'last': 'Lennon'})
 |      >>> db.insert({'first': 'Paul', 'last': 'McCartney'}, duplicates='ignore')
 |
 |      See Also:
 |      ---------
 |      insertmany : Method for inserting a list of items.
 |
 |  insertmany(self, items, duplicates=False, _dump=True)
 |      Insert multiple JSON items into the database.
 |
 |      Parameters:
 |      -----------
 |      items : list
 |          A list of items to add to the database. Each item should be a dictionary
 |          representing a JSON object.
 |
 |      duplicates : bool or str, optional
 |          Specifies how to handle duplicate items if a unique index exists.
 |          Options are:
 |          - False (default): Raises an error if a duplicate is found.
 |          - True or "replace": Replaces existing items that violate a unique index.
 |          - "ignore": Ignores items that violate a unique index.
 |
 |      _dump : bool, optional
 |          If True (default), converts items to JSON strings before insertion.
 |          Set to False if the input is already a JSON string.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Raises:
 |      -------
 |      ValueError
 |          If `duplicates` is not one of {True, False, "replace", "ignore"}.
 |
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> items = [
 |      ...     {'first': 'John', 'last': 'Lennon', 'birthdate': 1940},
 |      ...     {'first': 'Paul', 'last': 'McCartney', 'birthdate': 1942},
 |      ...     {'first': 'George', 'last': 'Harrison', 'birthdate': 1943}
 |      ... ]
 |      >>> db.insertmany(items, duplicates='ignore')
 |
 |      This will insert the list of JSON objects into the database, ignoring any
 |      duplicates if a unique index constraint exists.
 |
 |  items(self, _load=True)
 |      Return an iterator over all items in the database. The order is not guaranteed.
 |
 |      Parameters:
 |      -----------
 |      _load : bool, optional
 |          Determines whether to load the results as JSON objects. Defaults to True.
 |
 |      Returns:
 |      --------
 |      QueryResult
 |          An iterator of DBDicts, each representing a JSON object in the database.
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insertmany([{'first': 'John', 'last': 'Lennon'}, {'first': 'Paul', 'last': 'McCartney'}])
 |      >>> for item in db.items():
 |      ...     print(item)
 |      {'first': 'John', 'last': 'Lennon'}
 |      {'first': 'Paul', 'last': 'McCartney'}
 |
 |      This example iterates over all items in the database.
 |
 |  one = query_one(self, *query_args, **query_kwargs)
 |
 |  patch(self, patchitem, *query_args, **query_kwargs)
 |      Apply a patch to all items matching the specified query criteria.
 |
 |      Parameters:
 |      -----------
 |      patchitem : dict
 |          The patch to apply. Follows the RFC-7396 MergePatch algorithm.
 |          Note: Setting a key's value to None removes that key from the object.
 |
 |      *query_args : positional arguments
 |          Arguments can be dictionaries of equality key:value pairs or advanced
 |          queries. Multiple are combined with AND logic.
 |
 |      **query_kwargs : keyword arguments
 |          Keywords that represent equality conditions. Multiple are combined with
 |          AND logic.
 |
 |      _dump : bool, optional
 |          If True (default), converts the patch item to a JSON string before applying.
 |          Set to False if the input is already a JSON string.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insert({'first': 'George', 'last': 'Martin', 'birthdate': 1926, 'role': 'producer'})
 |      >>> db.patch({'role': 'composer'}, first='George', last='Martin')
 |      >>> item = db.query_one(first='George', last='Martin')
 |      >>> print(item)
 |      {'first': 'George', 'last': 'Martin', 'birthdate': 1926, 'role': 'composer'}
 |
 |
 |      >>> db.patch({'role': None}, first='George', last='Martin')
 |      >>> item = db.query_one(first='George', last='Martin')
 |      >>> print(item)
 |      {'first': 'George', 'last': 'Martin', 'birthdate': 1926}
 |
 |      This example removes the key "role".
 |
 |      Limitations:
 |      -----------
 |      Because `None` is the keyword to remove the field, it cannot be used to set
 |      the value to None. This is an SQLite limitation.
 |
 |      References:
 |      -----------
 |      [1]: https://www.sqlite.org/json1.html#jpatch
 |
 |  path_counts(self, start=None)
 |      Return a dictionary of JSON paths and the count of items for each path.
 |
 |      Parameters:
 |      -----------
 |      start : str, tuple, or None, optional
 |          The starting path for counting keys. If None (default), counts all paths
 |          at the root level. Can be a string with '$' for a full path, a single key
 |          without '$', a tuple/list, or a Query object.
 |
 |      Returns:
 |      --------
 |      dict
 |          A dictionary where keys are JSON paths and values are the count of items
 |          at each path.
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insertmany([
 |      ...     {'first': 'John', 'last': 'Lennon', 'birthdate': 1940, 'address': {'city': 'New York', 'zip': '10001'}},
 |      ...     {'first': 'Paul', 'last': 'McCartney', 'birthdate': 1942, 'address': {'city': 'Liverpool', 'zip': 'L1 0AA'}},
 |      ...     {'first': 'George', 'last': 'Harrison', 'birthdate': 1943}
 |      ... ])
 |      >>> counts = db.path_counts()
 |      >>> print(counts)
 |      {'first': 3, 'last': 3, 'birthdate': 3, 'address': 2}
 |
 |      This example counts the number of occurrences of each key at the root level.
 |
 |      >>> address_counts = db.path_counts('address')
 |      >>> print(address_counts)
 |      {'city': 2, 'zip': 2}
 |
 |      This example counts the number of occurrences of each key within the 'address' object.
 |
 |  query(self, *query_args, **query_kwargs)
 |      Query the database for items matching specified criteria.
 |
 |      Parameters:
 |      -----------
 |      *query_args : positional arguments
 |          Arguments can be dictionaries of equality key:value pairs or advanced
 |          queries. Multiple are combined with AND logic. See "Query Forms" below.
 |
 |      **query_kwargs : keyword arguments
 |          Keywords that represent equality conditions. Multiple are combined with
 |          AND logic.
 |
 |      _load : bool, optional
 |          Determines whether to load the result as JSON objects. Defaults to True.
 |
 |      Returns:
 |      --------
 |      QueryResult
 |          An iterator of DBDicts, each representing a JSON object in the database.
 |
 |      Examples:
 |      ---------
 |      >>> db.query(first='John', last='Lennon')
 |      >>> db.query({'birthdate': 1940})
 |      >>> db.query((db.Q.first == "Paul") | (db.Q.first == "John"))
 |      >>> db.query((db.Q.first % "Geo%") & (db.Q.birthdate <= 1943))
 |
 |      See Also:
 |      ---------
 |      query_one : Method for querying a single item.
 |
 |      Query Forms:
 |      ------------
 |
 |      Queries can take some of the following forms:
 |        Keyword:
 |          db.query(key=val)
 |          db.query(key1=val1,key2=val2) # AND
 |
 |        Arguments:
 |          db.query({'key':val})
 |
 |          db.query({'key1':val1,'key2':val2}) # AND
 |          db.query({'key1':val1,},{'key2':val2}) # AND (same as above)
 |
 |      Nested queries can be accomplished with arguments. The key can take
 |      the following forms:
 |
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
 |          - Advaced queries via query objects (explained below)
 |
 |      Advanced queries allow for more comparisons. Note: You must be careful
 |      about parentheses for operations. Keys are assigned with attributes (dot)
 |      and/or items (brackets). Items can have multiple separated by a comma and
 |      can include integers for items within a list.
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
 |
 |          LIKE statements:  db.Q.key % "pat%tern"
 |          GLOB statements:  db.Q.key * "glob*pattern"
 |          REGEX statements: db.Q.key @ "regular.*expressions"
 |
 |      db.query() is also aliased to db() and db.search()
 |
 |  query_by_path_exists(self, path, _load=True)
 |      Return items iterator over items whos path exist. Paths can be nested
 |      and take the usual possible four forms (single-key string, SQLite
 |      JSON path, tuple, and/or query object).
 |
 |      Note that this is similar to
 |
 |          >>> db.query(db.Q.path != None)
 |
 |      but if you have items that are set as `None`, that query will miss it.
 |
 |      Parameters:
 |      -----------
 |      path : str or tuple
 |          The JSON path to check for existence. Can be a single-key string, a
 |          JSON path string, or a tuple representing a path.
 |
 |      _load : bool, optional
 |          Determines whether to load the result as JSON objects. Defaults to True.
 |
 |      Returns:
 |      --------
 |      QueryResult
 |          An iterator of DBDicts, each representing a JSON object in the database
 |          where the specified path exists.
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insert({'first': 'John', 'last': 'Lennon', 'details': {'birthdate': 1940}})
 |      >>> result = db.query_by_path_exists(('details', 'birthdate'))
 |      >>> for item in result:
 |      ...     print(item)
 |      {'first': 'John', 'last': 'Lennon', 'details': {'birthdate': 1940}}
 |
 |      This example queries for items where the path `details.birthdate` exists.
 |
 |  query_one(self, *query_args, **query_kwargs)
 |      Query the database and return a single item matching the criteria.
 |
 |      Parameters:
 |      -----------
 |      *query_args : positional arguments
 |          Arguments can be dictionaries of equality key:value pairs or advanced
 |          queries. Multiple are combined with AND logic. See query() for details
 |
 |      **query_kwargs : keyword arguments
 |          Keywords that represent equality conditions. Multiple are combined with
 |          AND logic.
 |
 |      Returns:
 |      --------
 |      DBDict or None
 |          A single DBDict object representing the JSON item, or None if no match is
 |          found.
 |
 |      Examples:
 |      ---------
 |      >>> db.query_one(first='John', last='Lennon')
 |
 |      See Also:
 |      ---------
 |      query : Method for querying multiple items.
 |
 |  remove(self, *query_args, **query_kwargs)
 |      Remove items from the database matching the specified query criteria.
 |
 |      Parameters:
 |      -----------
 |      *query_args : positional arguments
 |          Arguments can be dictionaries of equality key:value pairs or advanced
 |          queries. Multiple are combined with AND logic.
 |
 |      **query_kwargs : keyword arguments
 |          Keywords that represent equality conditions. Multiple are combined with
 |          AND logic.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Examples:
 |      ---------
 |      >>> db.remove(first='George')
 |
 |  remove_by_rowid(self, *rowids)
 |      Remove items from the database by their rowid.
 |
 |      Parameters:
 |      -----------
 |      *rowids : int
 |          One or more rowids of the items to be removed.
 |
 |      Returns:
 |      --------
 |      None
 |
 |      Examples:
 |      ---------
 |      >>> db = JSONLiteDB(':memory:')
 |      >>> db.insert({'first': 'Ringo', 'last': 'Starr', 'birthdate': 1940})
 |      >>> item = db.query_one(first='Ringo', last='Starr')
 |      >>> db.remove_by_rowid(item.rowid)
 |
 |      This example removes an item from the database using its rowid.
 |
 |  search = query(self, *query_args, **query_kwargs)
 |
 |  search_one = query_one(self, *query_args, **query_kwargs)
 |
 |  update(self, item, rowid=None, duplicates=False, _dump=True)
 |      Update an existing item in the database.
 |
 |      Parameters:
 |      -----------
 |      item : dict
 |          The item to update in the database.
 |
 |      rowid : int, optional
 |          The rowid of the item to update. If not specified, inferred from the item's
 |          'rowid' attribute.
 |
 |      duplicates : bool or str, optional
 |          Specifies how to handle duplicate items if a unique index exists.
 |          Options are:
 |          - False (default): Raises an error if a duplicate is found.
 |          - True or "replace": Replaces existing items that violate a unique index.
 |          - "ignore": Ignores items that violate a unique index.
 |
 |      _dump : bool, optional
 |          If True (default), converts the item to a JSON string before updating.
 |          Set to False if the input is already a JSON string.
 |
 |      Raises:
 |      -------
 |      MissingRowIDError
 |          If rowid is not specified and cannot be inferred.
 |
 |      ValueError
 |          If `duplicates` is not one of {True, False, "replace", "ignore"}.
 |
 |      Examples:
 |      ---------
 |      >>> db.update({'first': 'George', 'last': 'Harrison', 'birthdate': 1943}, rowid=1)
 |
 |  ----------------------------------------------------------------------
 |  Class methods defined here:
 |
 |  connect(*args, **kwargs)
 |      Create and return a new JSONLiteDB connection.
 |
 |      This is a class method that acts as a shortcut for __init__.
 |
 |      Parameters:
 |      -----------
 |      *args : positional arguments
 |          Arguments to pass to the constructor.
 |      **kwargs : keyword arguments
 |          Keyword arguments to pass to the constructor.
 |
 |      Returns:
 |      --------
 |      JSONLiteDB
 |          A new instance of JSONLiteDB.
 |
 |  open = connect(*args, **kwargs)
 |      Create and return a new JSONLiteDB connection.
 |
 |      This is a class method that acts as a shortcut for __init__.
 |
 |      Parameters:
 |      -----------
 |      *args : positional arguments
 |          Arguments to pass to the constructor.
 |      **kwargs : keyword arguments
 |          Keyword arguments to pass to the constructor.
 |
 |      Returns:
 |      --------
 |      JSONLiteDB
 |          A new instance of JSONLiteDB.
 |
 |  read_only(dbpath, **kwargs)
 |      Open a JSONLiteDB connection in read-only mode. Shortcut For
 |          JSONLiteDB(f"file:{dbpath}?mode=ro",uri=True,**kwargs)
 |      where **kwargs can contain both JSONLiteDB and sqlite3 kwargs
 |
 |      Parameters:
 |      -----------
 |      dbpath : str
 |          Path to the SQLite database file.
 |      **kwargs : keyword arguments
 |          Additional keyword arguments for JSONLiteDB and sqlite3.
 |
 |      Returns:
 |      --------
 |      JSONLiteDB
 |          A new instance of JSONLiteDB in read-only mode.
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
 |      dictionary for instance variables
 |
 |  __weakref__
 |      list of weak references to the object

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
 |  __and__ = _method(self, other, *, comb='AND') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __call__(self)
 |      Enable it to be called. Lessens mistakes when used as property of db
 |
 |  __eq__ = _method(self, val, *, sym='=') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __ge__ = _method(self, val, *, sym='>=') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __getattr__(self, attr)
 |      ## Key Builders
 |
 |  __getitem__(self, item)
 |
 |  __gt__ = _method(self, val, *, sym='>') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __init__(self)
 |      Initialize self.  See help(type(self)) for accurate signature.
 |
 |  __invert__(self)
 |
 |  __le__ = _method(self, val, *, sym='<=') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __lt__ = _method(self, val, *, sym='<') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __matmul__ = _method(self, val, *, sym='REGEXP') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __mod__ = _method(self, val, *, sym='LIKE') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __mul__ = _method(self, val, *, sym='GLOB') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __ne__ = _method(self, val, *, sym='!=') from functools.partialmethod._make_unbound_method.<locals>
 |
 |  __or__ = _method(self, other, *, comb='OR') from functools.partialmethod._make_unbound_method.<locals>
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
 |      dictionary for instance variables
 |
 |  __weakref__
 |      list of weak references to the object
 |
 |  ----------------------------------------------------------------------
 |  Data and other attributes defined here:
 |
 |  __hash__ = None

```