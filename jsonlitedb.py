#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import datetime
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import sys
from collections import namedtuple
from functools import partialmethod
from pathlib import Path
from textwrap import dedent

logger = logging.getLogger(__name__)
sqllogger = logging.getLogger(__name__ + "-sql")

__version__ = "0.1.9"

__all__ = ["JSONLiteDB", "Q", "Query", "sqlite_quote", "Row"]

if sys.version_info < (3, 8):  # pragma: no cover
    raise ImportError("Must use Python >= 3.8")

DEFAULT_TABLE = "items"


class JSONLiteDB:
    """
    JSON(Lines) SQLite Database. Simple SQLite3 backed JSON document database with
    powerful queries and indexing.

    Initialize a JSONLiteDB instance.

    Parameters:
    -----------
    dbpath : str or Path or sqlite3.Connection
        Path to the SQLite database file. Use ':memory:' for an in-memory database.
        If given an sqlite3.Connection, will use that and ignore sqlitekws

    wal_mode : bool, optional
        Whether to use write-ahead-logging (WAL) mode. Defaults to True.
        ADVANCED: Can also set this directly with the execute() method as needed.

    table : str, optional
        Name of the database table to use. Defaults to 'items'.

    **sqlitekws : keyword arguments
        Additional keyword arguments passed to sqlite3.connect. See [1] for
        more details.

    Raises:
    -------
    sqlite3.Error
        If there is an error connecting to the database.

    Examples:
    ---------
    >>> db = JSONLiteDB(':memory:')
    >>> db = JSONLiteDB('my/database.db',table='Beatles')
    >>> db = JSONLiteDB('data.db',check_same_thread=False)

    References:
    -----------
    [1] https://docs.python.org/3/library/sqlite3.html#module-functions

    """

    def __init__(
        self,
        /,
        dbpath,
        wal_mode=True,
        table=DEFAULT_TABLE,
        **sqlitekws,
    ):
        if isinstance(dbpath, Path):
            dbpath = str(dbpath)

        if isinstance(dbpath, sqlite3.Connection):
            self.dbpath = "*existing connection*"
            self.db = dbpath
            self.sqlitekws = {}
        else:
            self.dbpath = dbpath
            self.sqlitekws = sqlitekws
            self.db = sqlite3.connect(self.dbpath, **sqlitekws)

        self.db.row_factory = Row
        self.db.set_trace_callback(sqldebug)
        self.db.create_function("REGEXP", 2, regexp, deterministic=True)

        self.table = "".join(c for c in table if c == "_" or c.isalnum())
        logger.debug(f"{self.table = }")

        self.context_count = 0

        self._init(wal_mode=wal_mode)

    @classmethod
    def connect(cls, *args, **kwargs):
        """
        Create and return a new JSONLiteDB connection.

        This is a class method that acts as a shortcut for __init__.

        Parameters:
        -----------
        *args : positional arguments
            Arguments to pass to the constructor.

        **kwargs : keyword arguments
            Keyword arguments to pass to the constructor.

        Returns:
        --------
        JSONLiteDB
            A new instance of JSONLiteDB.
        """
        return cls(*args, **kwargs)

    open = connect

    @classmethod
    def read_only(cls, dbpath, **kwargs):
        """
        Open a JSONLiteDB connection in read-only mode. Shortcut For
            JSONLiteDB(f"file:{dbpath}?mode=ro",uri=True,**kwargs)
        where **kwargs can contain both JSONLiteDB and sqlite3 kwargs

        Parameters:
        -----------
        dbpath : str
            Path to the SQLite database file.

        **kwargs : keyword arguments
            Additional keyword arguments for JSONLiteDB and sqlite3.

        Returns:
        --------
        JSONLiteDB
            A new instance of JSONLiteDB in read-only mode.
        """
        dbpath = f"file:{dbpath}?mode=ro"
        kwargs["uri"] = True
        return cls(dbpath, **kwargs)

    @classmethod
    def memory(cls, **kwargs):
        """
        Create an in-memory JSONLiteDB instance. Shortcut For
            JSONLiteDB(":memory:",**kwargs)
        where **kwargs can contain both JSONLiteDB and sqlite3 kwargs

        Parameters:
        -----------
        **kwargs : keyword arguments
            Additional keyword arguments for JSONLiteDB and sqlite3.

        Returns:
        --------
        JSONLiteDB
            A new instance of JSONLiteDB in memory.
        """
        return cls(":memory:", **kwargs)

    def insert(self, *items, duplicates=False, _dump=True):
        """
        Insert one or more JSON items into the database.

        Parameters:
        -----------
        *items : variable length argument list
            Items to add to the database. Each item should be a dictionary representing
            a JSON object.

        duplicates : bool or str, optional
            Specifies how to handle duplicate items if a unique index exists.
            Options are:
            - False (default): Raises an error if a duplicate is found.
            - True or "replace": Replaces existing items that violate a unique index.
            - "ignore": Ignores items that violate a unique index.

        _dump : bool, optional
            If True (default), converts items to JSON strings before insertion.
            Set to False if the input is already a JSON string.

        Returns:
        --------
        None

        Raises:
        -------
        ValueError
            If `duplicates` is not one of {True, False, "replace", "ignore"}.

        Examples:
        ---------
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'John', 'last': 'Lennon'})
        >>> db.insert({'first': 'Paul', 'last': 'McCartney'}, duplicates='ignore')

        See Also:
        ---------
        insertmany : Method for inserting a list of items.
        """
        return self.insertmany(items, duplicates=duplicates, _dump=_dump)

    add = insert

    def insertmany(self, items, duplicates=False, _dump=True):
        """
        Insert multiple JSON items into the database.

        Parameters:
        -----------
        items : list
            A list of items to add to the database. Each item should be a dictionary
            representing a JSON object.

        duplicates : bool or str, optional
            Specifies how to handle duplicate items if a unique index exists.
            Options are:
            - False (default): Raises an error if a duplicate is found.
            - True or "replace": Replaces existing items that violate a unique index.
            - "ignore": Ignores items that violate a unique index.

        _dump : bool, optional
            If True (default), converts items to JSON strings before insertion.
            Set to False if the input is already a JSON string.

        Returns:
        --------
        None

        Raises:
        -------
        ValueError
            If `duplicates` is not one of {True, False, "replace", "ignore"}.

        >>> db = JSONLiteDB(':memory:')
        >>> items = [
        ...     {'first': 'John', 'last': 'Lennon', 'birthdate': 1940},
        ...     {'first': 'Paul', 'last': 'McCartney', 'birthdate': 1942},
        ...     {'first': 'George', 'last': 'Harrison', 'birthdate': 1943}
        ... ]
        >>> db.insertmany(items, duplicates='ignore')

        This will insert the list of JSON objects into the database, ignoring any
        duplicates if a unique index constraint exists.
        """
        if not duplicates:
            rtxt = ""
        elif duplicates is True or duplicates == "replace":
            rtxt = "OR REPLACE"
        elif duplicates == "ignore":
            rtxt = "OR IGNORE"
        else:
            raise ValueError('Replace must be in {True, False, "replace", "ignore"}')

        items = listify(items)
        if _dump:
            ins = ([json.dumps(item, ensure_ascii=False)] for item in items)
        else:
            ins = ([item] for item in items)
        with self:
            self.executemany(
                f"""
                INSERT {rtxt} INTO {self.table} (data)
                VALUES (JSON(?))
                """,
                ins,
            )

    def query(self, *query_args, **query_kwargs):
        """
        Query the database for items matching specified criteria.

        Parameters:
        -----------
        *query_args : positional arguments
            Arguments can be dictionaries of equality key:value pairs or advanced
            queries. Multiple are combined with AND logic. See "Query Forms" below.

        **query_kwargs : keyword arguments
            Keywords that represent equality conditions. Multiple are combined with
            AND logic.

        _load : bool, optional
            Determines whether to load the result as JSON objects. Defaults to True.

        _limit : int, optional
            Adds a "LIMIT <N>" statement to the query. Useful to speed up queries. Note
            that will always still return the iterator. See query_one() for a method that
            returns just the first item

        _orderby: str, tuples, Query objects
            Specify how to order the results. If not specified, no ordering is
            requested. See "Order By" below.

        Returns:
        --------
        QueryResult
            An iterator of DBDict or DBList object, each representing a JSON object
            in the database. DBDict and DBList are just like normal dicts or lists but
            allow for the 'rowid' attribute.

        Examples:
        ---------
        >>> db.query(first='John', last='Lennon')
        >>> db.query({'birthdate': 1940})
        >>> db.query((db.Q.first == "Paul") | (db.Q.first == "John"))
        >>> db.query((db.Q.first % "Geo%") & (db.Q.birthdate <= 1943))

        See Also:
        ---------
        query_one : Method for querying a single item.

        Query Forms:
        ------------
        Queries can take some of the following forms:
          Keyword:

          >>> db.query(key=val)
          >>> db.query(key1=val1,key2=val2) # AND

          Arguments:

          >>> db.query({'key':val})

          >>> db.query({'key1':val1,'key2':val2}) # AND
          >>> db.query({'key1':val1,},{'key2':val2}) # AND (same as above)

        Nested queries can be accomplished with arguments. The key can take
        the following forms:

          1. String starting with "$" and follows SQLite's JSON path. Must properly quote
             if it has dots, etc. No additional quoting is performed

             >>> {"$.key":'val'}            # Single key
             >>> {"$.key.subkey":'val'}     # Nested keys
             >>> {"$.key.subkey[3]":'val'}  # Nested keys to nested list.

          2. Tuple string-keys or integer items. The quoting will be handled for you.

             >>> {('key',): 'val'}
             >>> {('key','subkey'): 'val'}
             >>> {('key','subkey',3): 'val'}

          3. Advanced queries via query objects (explained below)

        Advanced queries allow for more comparisons. Note: You must be careful
        about parentheses for operations. Keys are assigned with attributes (dot)
        and/or items (brackets). Items can have multiple separated by a comma and
        can include integers for items within a list. Let 'db' be the JSONLiteDB object.

          >>> db.query(db.Q.key == val)
          >>> db.query(db.Q['key'] == val)

          >>> db.query(db.Q.key.subkey == val)
          >>> db.query(db.Q['key'].subkey == val)
          >>> db.query(db.Q.key.['subkey'] == val)
          >>> db.query(db.Q['key','subkey'] == val)

          >>> qb.query(db.Q.key.subkey[3] == val)
          >>> qb.query(db.Q.key['subkey',3] == val)

        Complex Example:

          >>> db.query((db.Q['other key',9] >= 4) & (Q().key < 3)) # inequality

        Queries support most comparison operations (==, !=, >,>=,<, <=, etc) plus:

            LIKE statements:  db.Q.key % "pat%tern"
            GLOB statements:  db.Q.key * "glob*pattern"
            REGEX statements: db.Q.key @ "regular.*expression"  # See note

        Note regular expressions ("@") use Python's 're' library. These are often slower
        than LIKE ('%') and GLOB ('*') queries which use native SQLite queries.

        Warning:
            While the various constructions may be *functionally* the same (e.g.
            '$.key.subkey' vs ('key','subkey')), when using indexes, they will not
            be the same!

        db.query() is also aliased to db() and db.search()

        Order By:
        ---------
        Specify how to order the results with an SQL ORDER BY clause.

        Much like query, but without the comparison (e.g. equality), it can take a few
        forms. The biggest difference is that a "-" or "+" be proceed it to specify order

        1. String starting with "$" and follows SQLite's JSON path. Must properly quote
           if it has dots, etc. No additional quoting is performed. A preceding - mean
           DESC and + means ASC but isn't needed

           >>> "$.key"
           >>> "$.key.subkey"
           >>> "$.key.subkey[3]"

           >>> "-$.key"
           >>> "-$.key.subkey"
           >>> "-$.key.subkey[3]"

        2. String without '$' meaning it will be escaped and quoted. ADD NEG DESC

           >>> "key"
           >>> "-key"

        3. Tuple string-keys or integer items. The quoting will be handled for you. The
           first, and only the first, item can have a "-" in front to set the orderby

            >>> ('key',)
            >>> ('key','subkey')
            >>> ('key','subkey',3)

            >>> ('-key',)
            >>> ('-key','subkey')
            >>> ('-key','subkey',3)

            WARNING: It must be a tuple as a list will infer multiple items.
            WARNING: Only the first item may be +/-

        4. Advanced queries via query objects. Similar to above but without comparison

           >>> db.Q.key
           >>> db.Q.key.subkey
           >>> db.Q.key.subkey[3]

           >>> -db.Q.key
           >>> -db.Q.key.subkey
           >>> -db.Q.key.subkey[3]

        You can also specify a list of items to set the order

            ["-key1", "db.Q.key2", ('-key3','subkey')]

        A preceding + is ASC (default) and a - is DESC. A - can only be on the first
        item in a tuple or before the '$' if given a string
        """
        _load = query_kwargs.pop("_load", True)
        _limit = query_kwargs.pop("_limit", None)
        _orderby = query_kwargs.pop("_orderby", None)

        order = self._orderby2sql(_orderby)
        limit = f"LIMIT {_limit:d}" if _limit else ""

        qstr, qvals = JSONLiteDB._query2sql(*query_args, **query_kwargs)
        res = self.execute(
            f"""
            SELECT rowid, data FROM {self.table} 
            WHERE
                {qstr}
            {order}
            {limit}
            """,
            qvals,
        )

        return QueryResult(res, _load=_load)

    __call__ = search = query

    def query_one(self, *query_args, **query_kwargs):
        """
        Query the database and return a single item matching the criteria.

        The only difference between this and query() is that query_one adds
        "LIMIT 1" to the query.

        Parameters:
        -----------
        *query_args : positional arguments
            Arguments can be dictionaries of equality key:value pairs or advanced
            queries. Multiple are combined with AND logic. See query() for details

        **query_kwargs : keyword arguments
            Keywords that represent equality conditions. Multiple are combined with
            AND logic.

        Returns:
        --------
        DBDict, DBList or None
            A single DBDict or DBList object representing the JSON item, or None
            if no match is found.

        Examples:
        ---------
        >>> db.query_one(first='John', last='Lennon')

        See Also:
        ---------
        query : Method for querying multiple items.
        """
        query_kwargs["_limit"] = 1
        try:
            return next(self.query(*query_args, **query_kwargs))
        except StopIteration:
            return None

    search_one = one = query_one

    def count(self, *query_args, **query_kwargs):
        """
        Count the number of items matching the query criteria. This uses SQLite to
        count and is faster than counting the items returned in a query.

        Parameters:
        -----------
        *query_args : positional arguments
            Arguments can be dictionaries of equality key:value pairs or advanced
            queries. Multiple are combined with AND logic. See query() for details.

        **query_kwargs : keyword arguments
            Keywords that represent equality conditions. Multiple are combined with
            AND logic.

        Returns:
        --------
        int
            The number of items matching the query criteria.

        Examples:
        ---------
        >>> db.count(first='George')
        """
        qstr, qvals = JSONLiteDB._query2sql(*query_args, **query_kwargs)

        res = self.execute(
            f"""
            SELECT COUNT(rowid) FROM {self.table} 
            WHERE
                {qstr}
            """,
            qvals,
        ).fetchone()
        return res[0]

    def query_by_path_exists(self, path, _load=True, _orderby=None):
        """
        Return items iterator over items whos path exist. Paths can be nested
        and take the usual possible four forms (single-key string, SQLite
        JSON path, tuple, and/or query object).

        Note that this is similar to

            >>> db.query(db.Q.path != None)

        but if you have items that are set as `None`, that query will miss it.

        Parameters:
        -----------
        path : str or tuple
            The JSON path to check for existence. Can be a single-key string, a
            JSON path string, or a tuple representing a path.

        _load : bool, optional
            Determines whether to load the result as JSON objects. Defaults to True.

        _orderby
            How to order the results. See query() for details

        Returns:
        --------
        QueryResult
            An iterator of DBDicts, each representing a JSON object in the database
            where the specified path exists.

        Examples:
        ---------
        The following example queries for items where the path `details.birthdate` exists.
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'John', 'last': 'Lennon', 'details': {'birthdate': 1940}})
        >>> result = db.query_by_path_exists(('details', 'birthdate'))
        >>> for item in result:
        ...     print(item)
        {'first': 'John', 'last': 'Lennon', 'details': {'birthdate': 1940}}
        """

        path = split_query(path)
        if len(path) == 0:
            parent = Query()
            child = ""
        elif len(path) == 1:
            parent = Query()
            child = path[0]
        else:
            parent = path[:-1]
            child = path[-1]

        parent = build_index_paths(parent)[0]

        order = self._orderby2sql(_orderby)

        res = self.execute(
            f"""
            SELECT DISTINCT
                -- Because JSON_EACH is table-valued, we will have repeats.
                -- Just doing DISTINCT on 'data' is bad because it will
                -- block desired duplicate rows. Include rowid to go by full row
                {self.table}.rowid,
                {self.table}.data
            FROM
                {self.table},
                JSON_EACH({self.table}.data,?) as each
            WHERE
                each.key = ?
            {order}
            """,
            (parent, child),
        )
        return QueryResult(res, _load=_load)

    def aggregate(self, path, /, function):
        """
        Compute an aggregate function over a specified JSON path.

        Parameters:
        -----------
        path : str or tuple
            The JSON path to aggregate. Can be a string or tuple representing the path.

        function : str
            The aggregate function to apply. Options are 'AVG', 'COUNT', 'MAX', 'MIN',
            'SUM', or 'TOTAL'.

        Returns:
        --------
        float or int
            The result of the aggregate function applied to the specified path.

        Raises:
        -------
        ValueError
            If an unallowed aggregate function is specified.

        Examples:
        ---------
        The following example calculates the average of the 'value' field across
        all items.

        >>> db = JSONLiteDB(':memory:')
        >>> db.insertmany([{'value': 10}, {'value': 20}, {'value': 30}])
        >>> avg_value = db.aggregate('value', 'AVG')
        >>> print(avg_value)
        20.0

        OR

        >>> db.AVG('value') # 20.0 Same as above
        """
        allowed = {"AVG", "COUNT", "MAX", "MIN", "SUM", "TOTAL"}
        function = function.upper()
        if function not in allowed:
            raise ValueError(f"Unallowed aggregate function {function!r}")

        path = build_index_paths(path)[0]  # Always just one
        res = self.execute(
            f"""
            SELECT {function}(JSON_EXTRACT({self.table}.data, {sqlite_quote(path)})) 
            AS val FROM {self.table}
            """
        )

        return res.fetchone()["val"]

    AVG = partialmethod(aggregate, function="AVG")
    COUNT = partialmethod(aggregate, function="COUNT")
    MAX = partialmethod(aggregate, function="MAX")
    MIN = partialmethod(aggregate, function="MIN")
    SUM = partialmethod(aggregate, function="SUM")
    TOTAL = partialmethod(aggregate, function="TOTAL")

    def _explain_query(self, *query_args, **query_kwargs):
        """Explain the query. Used for testing"""
        _orderby = query_kwargs.pop("_orderby", None)
        order = self._orderby2sql(_orderby)

        qstr, qvals = JSONLiteDB._query2sql(*query_args, **query_kwargs)

        res = self.execute(
            f"""
            EXPLAIN QUERY PLAN
            SELECT data FROM {self.table} 
            WHERE
                {qstr}
            {order}
            """,
            qvals,
        )
        return [dict(row) for row in res]

    def remove(self, *query_args, **query_kwargs):
        """
        Remove items from the database matching the specified query criteria.

        WARNING: Not specifying any queries will purge the database!

        Parameters:
        -----------
        *query_args : positional arguments
            Arguments can be dictionaries of equality key:value pairs or advanced
            queries. Multiple are combined with AND logic.

        **query_kwargs : keyword arguments
            Keywords that represent equality conditions. Multiple are combined with
            AND logic.

        Returns:
        --------
        None

        Examples:
        ---------
        >>> db.remove(first='George')
        """
        qstr, qvals = JSONLiteDB._query2sql(*query_args, **query_kwargs)

        with self:
            self.execute(
                f"""
                DELETE FROM {self.table} 
                WHERE
                    {qstr}
                """,
                qvals,
            )

    def purge(self):
        """
        Remove all items from the database.

        Returns:
        --------
        None

        Examples:
        ---------
        >>> db.purge()
        >>> len(db)
        0
        """
        self.remove()

    def remove_by_rowid(self, *rowids):
        """
        Remove items from the database by their rowid.

        Parameters:
        -----------
        *rowids : int
            One or more rowids of the items to be removed.

        Returns:
        --------
        None

        Examples:
        ---------
        The following removes an item from the database using its rowid.
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'Ringo', 'last': 'Starr', 'birthdate': 1940})
        >>> item = db.query_one(first='Ringo', last='Starr')
        >>> db.remove_by_rowid(item.rowid)
        """
        with self:
            self.executemany(
                f"""
                DELETE FROM {self.table} 
                WHERE
                    rowid = ?
                """,
                ((rowid,) for rowid in rowids),
            )

    delete = remove
    delete_by_rowid = remove_by_rowid

    def __delitem__(self, rowid):
        """
        Delete an item with a given rowid

        Parameters
        ----------
        rowid : int
            The rowid of the item to deleye. Must correspond to a valid SQLite rowid
            (note that rowids start at 1).

        Raises
        ------
        TypeError
            If ``rowid`` is a tuple. Only a single item can be deleted at a time.
            See remove_by_rowid() to delete multiples

        IndexError
            If no item exists with the given rowid.

        See Also
        --------
        remove_by_rowid : Lower-level delete/remove method. Accepts multiple rowids and
                          does not raise an IndexError

        Examples
        --------
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'George', 'last': 'Martin'})
        >>> del db[1] # rowids start at 1
        >>> len(db)
        0

        """
        if isinstance(rowid, tuple):
            raise TypeError("Can only delete one item at a time. Try delete()")

        check = self.execute(
            f"SELECT 1 FROM  {self.table} WHERE rowid = ? LIMIT 1", (rowid,)
        ).fetchone()

        if not check:
            raise IndexError(f"{rowid = } not found")

        return self.remove_by_rowid(rowid)

    def get_by_rowid(self, rowid, *, _load=True):
        """
        Retrieve an item from the database by its rowid.

        Parameters:
        -----------
        rowid : int
            The rowid of the item to retrieve.

        _load : bool, optional
            Determines whether to load the result as a JSON object. Defaults to True.

        Returns
        -------
        DBDict or DBList or object
            The item retrieved from the database. The type depends on the stored data:
            - ``DBDict`` if the item is a JSON object (dict).
            - ``DBList`` if the item is a JSON array (list).
            - The raw value otherwise.
            DBDict and DBList objects are just like dict and list but have a 'rowid'
            attribute

        Examples:
        ---------
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'George', 'last': 'Martin', 'birthdate': 1926})
        >>> item = db.query_one(first='George', last='Martin')
        >>> print(db.get_by_rowid(item.rowid))
        {'first': 'George', 'last': 'Martin', 'birthdate': 1926}

        """
        row = self.execute(
            f"""
            SELECT rowid,data 
            FROM {self.table} 
            WHERE
                rowid = ?
            """,
            (rowid,),
        ).fetchone()

        if not row:
            return

        if not _load:
            return row["data"]

        item = json.loads(row["data"])

        if isinstance(item, dict):
            item = DBDict(item)
        elif isinstance(item, list):
            item = DBList(item)
        else:
            return item
        item.rowid = row["rowid"]

        return item

    def __getitem__(self, rowid):
        """
        Retrieve an item from the database by its rowid.

        Parameters
        ----------
        rowid : int
            The rowid of the item to retrieve. Must correspond to a valid SQLite rowid
            (NOTE: rowids start at 1).

        Returns
        -------
        DBDict or DBList or object
            The item retrieved from the database. The type depends on the stored data:
            - ``DBDict`` if the item is a JSON object (dict).
            - ``DBList`` if the item is a JSON array (list).
            - The raw value otherwise.
            DBDict and DBList objects are just like dict and list but have a 'rowid'
            attribute

        Raises
        ------
        TypeError
            If ``rowid`` is a tuple. Only a single item can be retrieved at a time.
        IndexError
            If no item exists with the given rowid.

        See Also
        --------
        get_by_rowid : Lower-level retrieval method. Returns ``None`` instead of raising
            ``IndexError``.

        Examples
        --------
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'George', 'last': 'Martin'})
        >>> item = db.query_one(first='George', last='Martin')
        >>> db[item.rowid]
        {'first': 'George', 'last': 'Martin'}
        """
        if isinstance(rowid, tuple):
            raise TypeError("Can only get one item at a time")
        item = self.get_by_rowid(rowid)
        if item is None:  # Explicit for None to avoid empty dict raising error
            raise IndexError(f"{rowid = } not found")
        return item

    def items(self, _load=True):
        """
        Return an iterator over all items in the database. The order is not guaranteed.

        Parameters:
        -----------
        _load : bool, optional
            Determines whether to load the results as JSON objects. Defaults to True.

        Returns:
        --------
        QueryResult
            An iterator of DBDicts, each representing a JSON object in the database.

        Examples:
        ---------
        >>> db = JSONLiteDB(':memory:')
        >>> db.insertmany([
            {'first': 'John', 'last': 'Lennon'},
            {'first': 'Paul', 'last': 'McCartney'}
        ])
        >>> for item in db.items():
        ...     print(item)
        {'first': 'John', 'last': 'Lennon'}
        {'first': 'Paul', 'last': 'McCartney'}
        """
        res = self.execute(f"SELECT rowid, data FROM {self.table}")

        return QueryResult(res, _load=_load)

    __iter__ = items

    def update(self, item, rowid=None, duplicates=False, _dump=True):
        """
        Update an existing row in the database with new a new row.

        Parameters:
        -----------
        item : dict
            The item to update in the database.

        rowid : int, optional
            The rowid of the item to update. If not specified, inferred from the item's
            'rowid' attribute.

        duplicates : bool or str, optional
            Specifies how to handle duplicate items if a unique index exists.
            Options are:
            - False (default): Raises an error if a duplicate is found.
            - True or "replace": Replaces existing items that violate a unique index.
            - "ignore": Ignores items that violate a unique index.

        _dump : bool, optional
            If True (default), converts the item to a JSON string before updating.
            Set to False if the input is already a JSON string.

        Raises:
        -------
        MissingRowIDError
            If rowid is not specified and cannot be inferred.

        ValueError
            If `duplicates` is not one of {True, False, "replace", "ignore"}.

        See Also:
        --------
        patch: Apply a patch to all items matching the specified query criteria.

        Examples:
        ---------
        >>> db.update({'first': 'George', 'last': 'Harrison', 'birthdate': 1943}, rowid=1)
        """
        rowid = rowid or getattr(item, "rowid", None)  # rowid starts at 1

        if rowid is None:
            raise MissingRowIDError("Must specify rowid if it can't be infered")

        if _dump:
            item = json.dumps(item, ensure_ascii=False)

        if not duplicates:
            rtxt = ""
        elif duplicates is True or duplicates == "replace":
            rtxt = "OR REPLACE"
        elif duplicates == "ignore":
            rtxt = "OR IGNORE"
        else:
            raise ValueError('Replace must be in {True, False, "replace", "ignore"}')

        with self:
            self.execute(
                f"""
                UPDATE {rtxt} {self.table}
                SET
                    data = JSON(?)
                WHERE
                    rowid = ?
                """,
                (item, rowid),
            )

    def patch(self, patchitem, *query_args, **query_kwargs):
        """
        Apply a patch to all items matching the optionally specified query criteria.

        Parameters:
        -----------
        patchitem : dict
            The patch to apply. Follows the RFC-7396 [2] MergePatch algorithm.
            Note: Setting a key's value to None removes that key from the object.

        *query_args : positional arguments
            Arguments can be dictionaries of equality key:value pairs or advanced
            queries. Multiple are combined with AND logic. Note, if no query args or
            keywords are specified, will apply to all!

        **query_kwargs : keyword arguments
            Keywords that represent equality conditions of key=value. Multiple are
            combined with AND logic. Note, if no query args or keywords are specified,
            will apply to all!

        _dump : bool, optional
            If True (default), converts the patch item to a JSON string before applying.
            Set to False if the input is already a JSON string.

        Returns:
        --------
        None

        Examples:
        ---------
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'George', 'last': 'Martin', 'birthdate': 1926, 'role': 'producer'})
        >>> db.patch({'role': 'composer'}, first='George', last='Martin')
        >>> print(db.query_one(first='George', last='Martin'))
        {'first': 'George', 'last': 'Martin', 'birthdate': 1926, 'role': 'composer'}

        The following example removes the key "role".

        >>> db.patch({'role': None}, first='George', last='Martin')
        >>> print(db.query_one(first='George', last='Martin'))
        {'first': 'George', 'last': 'Martin', 'birthdate': 1926}

        The following example adds a field to *all* rows. Notice no query is specified

        >>> db.patch({'band':'The Beatles'})
        >>> print(db.count(band='The Beatles'))
        5

        Limitations:
        -----------
        Because `None` is the keyword to remove the field, it cannot be used to set
        the value to None. This is an SQLite (and RFC 7396) limitation. If this is
        needed, use a Python loop.

        References:
        -----------
        [1]: https://www.sqlite.org/json1.html#jpatch
        [2]: https://datatracker.ietf.org/doc/html/rfc7396
        """
        _dump = query_kwargs.pop("_dump", True)

        qstr, qvals = JSONLiteDB._query2sql(*query_args, **query_kwargs)

        if _dump:
            patchitem = json.dumps(patchitem, ensure_ascii=False)

        with self:
            self.execute(
                f"""
                UPDATE {self.table}
                SET data = JSON_PATCH(data,JSON(?))
                WHERE
                    {qstr}
                """,
                (patchitem, *qvals),
            )

    def path_counts(self, start=None):
        """
        Return a dictionary of JSON paths and the count of items for each path.

        Parameters:
        -----------
        start : str, tuple, or None, optional
            The starting path for counting keys. If None (default), counts all paths
            at the root level. Can be a string with '$' for a full path, a single key
            without '$', a tuple/list, or a Query object.

        Returns:
        --------
        dict
            A dictionary where keys are JSON paths and values are the count of items
            at each path.

        Examples:
        ---------
        The following counts the number of occurrences of each key at the root level.

        >>> db = JSONLiteDB(':memory:')
        >>> db.insertmany([
        ...     {'first': 'John', 'last': 'Lennon', 'birthdate': 1940, 'address': {'city': 'New York', 'zip': '10001'}},
        ...     {'first': 'Paul', 'last': 'McCartney', 'birthdate': 1942, 'address': {'city': 'Liverpool', 'zip': 'L1 0AA'}},
        ...     {'first': 'George', 'last': 'Harrison', 'birthdate': 1943}
        ... ])
        >>> print(db.path_counts())
        {'first': 3, 'last': 3, 'birthdate': 3, 'address': 2}

        The following example counts the number of occurrences of each key within the
        'address' object.

        >>> print(db.path_counts('address'))
        {'city': 2, 'zip': 2}
        """
        start = start or "$"
        start = build_index_paths(start)[0]  # Always just one
        res = self.execute(
            f"""
            SELECT 
                each.key, 
                COUNT(each.key) as count
            FROM 
                {self.table}, 
                JSON_EACH({self.table}.data,{sqlite_quote(start)}) AS each
            GROUP BY each.key
            ORDER BY -count
            """
        )
        counts = {row["key"]: row["count"] for row in res}
        counts.pop(None, None)  # do not include nothing
        return counts

    key_counts = path_counts

    def keys(self, start=None):
        """
        Return the set of keys (JSON paths) at the specified path.

        This is a shorthand for `path_counts(start).keys()` and returns only the
        keys found at the specified path in the JSON structure.

        Parameters
        ----------
        start : str, tuple, or None, optional
            The starting path to extract keys from. If None (default), keys at the
            root level are returned. Accepts the same input as `path_counts`.

        Returns
        -------
        KeysView
            A view object containing the keys (paths) at the specified location.

        Examples
        --------
        >>> db.keys()
        dict_keys(['first', 'last', 'birthdate', 'address'])

        >>> db.keys('address')
        dict_keys(['city', 'zip'])
        """
        return self.path_counts(start=start).keys()

    def create_index(self, *paths, unique=False):
        """
        Create an index on specified JSON paths to improve query performance.

        Parameters:
        -----------
        *paths : variable length argument list
            Paths to index. Can be strings, tuples, or query objects.

        unique : bool, optional
            If True, creates a unique index. Defaults to False.

        Returns:
        --------
        None

        Examples:
        ---------
        >>> db.create_index('first')                # Single Key

        >>> db.create_index('first','last')         # Multiple keys
        >>> db.create_index(db.Q.first,db.Q.last)   # Multiple advanced queries

        >>> db.create_index(('address','city'))     # Path with subkeys
        >>> db.create_index(db.Q.address.city)      # Path with subkeys

        >>> db.create_index(db.Q.addresses[1])      # Path w/ list index
        >>> db.create_index(('addresses',3))        # Equiv to above

        Note:
        -----
        sqlite3 is EXTREMELY sensitive to the form of the query. For example:
        db.create_index('key') and db.create_index('$.key'), which are identical in
        practice, will not use the same index. (This is because the former becomes
        '$."key"' which is not the same as '$.key').

        It is best to always use the same construction as query() to be certain.
        """
        paths = build_index_paths(*paths)

        index_name = (
            f"ix_{self.table}_" + hashlib.md5("=".join(paths).encode()).hexdigest()[:8]
        )
        if unique:
            index_name += "_UNIQUE"

        # sqlite3 prohibits parameters in index expressions so we have to
        # do this manually.
        quoted_paths = ",".join(
            f"JSON_EXTRACT(data, {sqlite_quote(path)})" for path in paths
        )
        with self:
            self.execute(
                f"""
                CREATE {"UNIQUE" if unique else ""} INDEX IF NOT EXISTS {index_name} 
                ON {self.table}(
                    {quoted_paths}
                )"""
            )

    def drop_index_by_name(self, name):
        """
        Delete an index from the database by its name.

        Parameters:
        -----------
        name : str
            The name of the index to be dropped.

        Returns:
        --------
        None

        Examples:
        ---------
        The following example creates an index on the 'first' and 'last' field, then
        drops it using its name.

        >>> db = JSONLiteDB(':memory:')
        >>> db.create_index('first', 'last')
        >>> print(db.indexes)
        {'ix_items_250e4243': ['$."first"', '$."last"']}

        >>> db.drop_index_by_name('ix_items_250e4243')
        >>> print(db.indexes)
        {}
        """
        with self:  # Aparently this also must be manually quoted
            self.execute(f"DROP INDEX IF EXISTS {sqlite_quote(name)}")

    def drop_index(self, *paths, unique=False):
        """
        Delete an index from the database by query paths.

        Parameters:
        -----------
        *paths : variable length argument list
            Paths for which the index was created. Can be strings, tuples, or query
             objects.

        unique : bool, optional
            Indicates whether the index was created as unique. Defaults to False.

        Returns:
        --------
        None

        Examples:
        ---------
        The following example creates a UNIQUE index on the 'first' and 'last' field,
        then shows that dropping it w/o unique=True fails to do so but works as expected
        when specified.

        >>> db = JSONLiteDB(':memory:')
        >>> db.create_index('first', 'last', unique=True)
        >>> print(db.indexes)
        {'ix_items_250e4243_UNIQUE': ['$."first"', '$."last"']}

        >>> db.drop_index('first', 'last') # Does nothing. Not the same index
        >>> print(db.indexes)
        {'ix_items_250e4243_UNIQUE': ['$."first"', '$."last"']}

        >>> db.drop_index('first', 'last', unique=True)
        >>> print(db.indexes)
        {}
        """
        paths = build_index_paths(*paths)
        index_name = (
            f"ix_{self.table}_" + hashlib.md5("=".join(paths).encode()).hexdigest()[:8]
        )
        if unique:
            index_name += "_UNIQUE"
        return self.drop_index_by_name(index_name)

    @property
    def indexes(self):
        res = self.execute(
            """
            SELECT name,sql 
            FROM sqlite_schema
            WHERE 
                type='index' AND tbl_name = ?
            ORDER BY rootpage""",
            (self.table,),
        )
        indres = {}
        for row in res:
            keys = re.findall(r"JSON_EXTRACT\(data,\s?'(.*?)'\s?\)", row["sql"])
            if not keys:
                continue
            indres[row["name"]] = keys
        return indres

    indices = indexes

    def about(self):
        r = self.execute(
            f"""
                SELECT * FROM {self.table}_kv 
                WHERE key = ? OR key = ?
                ORDER BY key""",
            ("created", "version"),
        ).fetchall()
        # Note it is ORDER BY so the order wont change
        created, version = [i["val"] for i in r]
        return _about_obj(created=created, version=version)

    def _init(self, wal_mode=True):
        db = self.db
        try:
            created, version = self.about()
            logger.debug(f"DB Exists: {created = } {version = }")
            return
        except:
            logger.debug("DB does not exists. Creating")

        with self:
            db.execute(
                dedent(
                    f"""
                CREATE TABLE IF NOT EXISTS {self.table}(
                    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT
                )"""
                )
            )
            db.execute(
                dedent(
                    f"""
                CREATE TABLE IF NOT EXISTS {self.table}_kv(
                    key TEXT PRIMARY KEY,
                    val TEXT
                )"""
                )
            )
            # 'key' is PRIMARY KEY so it will be ignored if already there.
            db.execute(
                dedent(
                    f"""
                INSERT OR IGNORE INTO {self.table}_kv VALUES (?,?)
                """
                ),
                ("created", datetime.datetime.now().astimezone().isoformat()),
            )
            db.execute(
                dedent(
                    f"""
                INSERT OR IGNORE INTO {self.table}_kv VALUES (?,?)
                """
                ),
                ("version", f"JSONLiteDB-{__version__}"),
            )

        if wal_mode:
            try:
                with self:
                    db.execute("PRAGMA journal_mode = wal")
            except sqlite3.OperationalError:  # pragma: no cover
                pass

    @staticmethod
    def _query2sql(*query_args, **query_kwargs):
        """
        Combine *query_args, **query_kwargs into an SQL string and assocciated
        qmarks values.
        """
        eq_args = []
        qargs = []
        for arg in query_args:
            if isinstance(arg, Query):
                qargs.append(arg)
            else:
                eq_args.append(arg)

        equalities = _query_tuple2jsonpath(*eq_args, **query_kwargs)
        qobj = None
        for key, val in equalities.items():
            if qobj:
                qobj &= Query._from_equality(key, val)
            else:
                qobj = Query._from_equality(key, val)

        # Add the query query_args
        for arg in qargs:
            if qobj:
                qobj &= arg
            else:
                qobj = arg

        if qobj is None:
            return "1 = 1", []
        if not qobj._query:
            raise MissingValueError("Must set an (in)equality for query")

        # Neet to replace all placeholders with '?' but we also need to do
        # it in the proper order. May move to named (dict) style in the future but
        # this works well enough.
        reQ = re.compile(r"(!>>.*?<<!)")
        qvals = reQ.findall(qobj._query)
        qvals = [qobj._qdict[k] for k in qvals]
        qstr = reQ.sub("?", qobj._query)
        return qstr, qvals

    def _orderby2sql(self, orderby):
        """
        Turns orderby into SQL
        """
        # JSON_EXTRACT(data, {sqlite_quote(path)})
        if not orderby:
            return ""
        pairs = build_orderby_pairs(orderby)
        out = []
        for path, order in pairs:
            out.append(
                " " * 14  # The indent isn't needed but it looks nicer
                + f"JSON_EXTRACT({self.table}.data, {sqlite_quote(path)}) {order}"
            )

        return "ORDER BY\n" + ",\n".join(out)

    @property
    def Query(self):
        return Query()

    Q = Query

    def __len__(self):
        """
        Return the number of items in the database.

        Returns:
        --------
        int
            The total number of JSON objects stored in the database.

        Examples:
        ---------
        >>> db = JSONLiteDB(':memory:')
        >>> db.insert({'first': 'John', 'last': 'Lennon'})
        >>> db.insert({'first': 'Paul', 'last': 'McCartney'})
        >>> print(len(db))
        2
        """
        res = self.execute(f"SELECT COUNT(rowid) FROM {self.table}").fetchone()
        return res[0]

    def close(self):
        """
        Close the database connection.

        This method should be called when the database is no longer needed to
        ensure that all resources are properly released.

        Returns:
        --------
        None

        Examples:
        ---------
        >>> db = JSONLiteDB('mydata.db')
        >>> db.close()
        """
        logger.debug("close")
        self.db.close()

    __del__ = close

    def wal_checkpoint(self, mode=None):
        """
        Execute a write-ahead-log checkpoint optionally a given mode.

        Parameters:
        -----------
        mode : None or str, optional
            Mode for checkpoint. See [1] for details. Default is None. Options
            are None, 'PASSIVE', 'FULL', 'RESTART', 'TRUNCATE'

        Returns:
        --------
        None

        References:
        -----------
        [1] https://sqlite.org/wal.html#ckpt
        """
        if not mode in {None, "PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError(f"Invalid {mode = } specified")
        mode = f"({mode})" if mode else ""
        try:
            with self:
                self.execute(f"PRAGMA wal_checkpoint{mode};")
        except sqlite3.DatabaseError as E:  # pragma: no cover
            logger.debug(f"WAL checkoint error {E!r}")

    def execute(self, *args, **kwargs):
        """
        Execute a SQL statement against the UNDERLYING sqlite3 database.

        This method is a wrapper around the `execute` method of the SQLite database
        connection, allowing you to run SQL statements directly on the database.

        Note that the sqlite3 connection is stored as the 'db' class variable and can be
        accessed directly.

        Parameters:
        -----------
        *args : tuple
            Positional arguments that specify the SQL command and any parameters
            to be used in the execution of the command.

        **kwargs : dict
            Keyword arguments that can be used to pass additional options for the
            execution of the SQL command.

        Returns:
        --------
        sqlite3.Cursor
            A cursor object that can be used to iterate over the results of the
            SQL query, if applicable.

        """
        return self.db.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        """
        Execute many SQL statements against the UNDERLYING sqlite3 database.

        This method is a wrapper around the `executemany` method of the SQLite database
        connection, allowing you to run SQL statements directly on the database.

        Note that the sqlite3 connection is stored as the 'db' class variable and can be
        accessed directly.

        Parameters:
        -----------
        *args : tuple
            Positional arguments that specify the SQL command and any parameters
            to be used in the execution of the command.

        **kwargs : dict
            Keyword arguments that can be used to pass additional options for the
            execution of the SQL command.

        Returns:
        --------
        sqlite3.Cursor
            A cursor object that can be used to iterate over the results of the
            SQL query, if applicable.

        """
        return self.db.executemany(*args, **kwargs)

    def __repr__(self):
        res = [f"JSONLiteDB("]
        res.append(f"{self.dbpath!r}")
        if self.table != DEFAULT_TABLE:
            res.append(f", table={self.table!r}")
        if self.sqlitekws:
            res.append(f", **{self.sqlitekws!r}")
        res.append(")")
        return "".join(res)

    __str__ = __repr__

    # These methods let you call the db as a context manager to do multiple transactions
    # but only commits if it is the last one. All internal methods call this one so as to
    # no commit before transactions are finished
    def __enter__(self):
        if self.context_count == 0:
            self.db.__enter__()
        self.context_count += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context_count -= 1
        if self.context_count == 0:
            self.db.__exit__(exc_type, exc_val, exc_tb)


# This allows us to have a dict but set an attribute called rowid.
class DBDict(dict):
    pass


class DBList(list):
    pass


class QueryResult:
    def __init__(self, res, _load=True):
        self.res = res
        self._load = _load

    def __iter__(self):
        return self

    def next(self):
        row = next(self.res)

        if not self._load:
            return row["data"]

        item = json.loads(row["data"])

        if isinstance(item, dict):
            item = DBDict(item)
        elif isinstance(item, list):
            item = DBList(item)
        else:
            return item
        item.rowid = row["rowid"]
        return item

    __next__ = next

    def fetchone(self):
        try:
            return next(self)
        except StopIteration:
            return

    one = fetchone

    def fetchall(self):
        return list(self)

    def fetchmany(self, size=None):
        if not size:
            size = self.res.arraysize
        out = []
        for _ in range(size):
            try:
                out.append(next(self))
            except StopIteration:
                break
        return out

    all = list = fetchall


def regexp(pattern, string):
    return bool(re.search(pattern, string))


class MissingValueError(ValueError):
    pass


class DissallowedError(ValueError):
    pass


class MissingRowIDError(ValueError):
    pass


class Query:
    """
    Query object to allow for more complex queries.
    """

    def __init__(self):
        self._key = []
        self._qdict = {}
        self._query = None  # Only gets set upon comparison or _from_equality
        self._asc_or_desc = None

    @staticmethod
    def _from_equality(k, v):
        self = Query()

        self._key = True  # To fool it
        qv = randkey()
        self._qdict[qv] = v
        # JSON_EXTRACT will accept a ? for the query but it will then break
        # usage with indices (and index creation will NOT accept ?). Therefore,
        # include it directly. Escape it still
        self._query = f"( JSON_EXTRACT(data, {sqlite_quote(k)}) = {qv} )"
        return self

    def __call__(self):
        """Enable it to be called. Lessens mistakes when used as property of db"""
        return self

    ## Key Builders
    def __getattr__(self, attr):  # Query().key
        self._key.append(attr)
        return self

    def __getitem__(self, item):  # Query()['key'] or Query()[ix]
        if isinstance(item, (list, tuple)):
            self._key.extend(item)
        else:
            self._key.append(item)
        return self

    def __add__(self, item):  # Allow Q() + 'key' -- Undocumented
        return self[item]

    def __setattr__(self, attr, val):
        if attr.startswith("_"):
            return super().__setattr__(attr, val)
        raise DissallowedError("Cannot set attributes. Did you mean '=='?")

    def __setitem__(self, attr, item):
        raise DissallowedError("Cannot set values. Did you mean '=='?")

    ## Comparisons
    def _compare(self, val, *, sym):
        if self._query:
            raise DissallowedError(
                "Cannot compare queries. For example, change "
                '"4 <= db.Q.val <= 5" to "(4 <= db.Q.val) & (db.Q.val <= 5)"'
            )

        r = _query_tuple2jsonpath({tuple(self._key): val})  # Will just return one item
        k, v = list(r.items())[0]

        if val is None and sym in {"=", "!="}:
            self._query = f"( JSON_EXTRACT(data, {sqlite_quote(k)}) IS {'NOT' if sym == '!=' else ''} NULL )"
            return self

        qv = randkey()
        self._qdict[qv] = v

        # JSON_EXTRACT will accept a ? for the query but it will then break
        # usage with indices (and index creation will NOT accept ?). Therefore,
        # include it directly. Escape it still
        self._query = f"( JSON_EXTRACT(data, {sqlite_quote(k)}) {sym} {qv} )"
        return self

    __lt__ = partialmethod(_compare, sym="<")
    __le__ = partialmethod(_compare, sym="<=")
    __eq__ = partialmethod(_compare, sym="=")
    __ne__ = partialmethod(_compare, sym="!=")
    __gt__ = partialmethod(_compare, sym=">")
    __ge__ = partialmethod(_compare, sym=">=")

    __mod__ = partialmethod(_compare, sym="LIKE")  # %
    __mul__ = partialmethod(_compare, sym="GLOB")  # *
    __matmul__ = partialmethod(_compare, sym="REGEXP")  # @

    ## Logic
    def _logic(self, other, *, comb):
        if not self._query or not other._query:
            raise MissingValueError("Must set an (in)equality before logic")

        self._qdict |= other._qdict
        self._query = f"( {self._query} {comb} {other._query} )"
        return self

    __and__ = partialmethod(_logic, comb="AND")
    __or__ = partialmethod(_logic, comb="OR")

    def __invert__(self):
        self._query = f"( NOT {self._query} )"
        return self

    # for ORDER BY
    def __neg__(self):
        self._asc_or_desc = "DESC"
        return self

    def __pos__(self):
        self._asc_or_desc = "ASC"
        return self

    def __str__(self):
        qdict = self._qdict
        if qdict or self._query:
            q = translate(self._query, {k: sqlite_quote(v) for k, v in qdict.items()})
        elif self._key:
            qdict = _query_tuple2jsonpath({tuple(self._key): None})
            k = list(qdict)[0]
            q = f"JSON_EXTRACT(data, {sqlite_quote(k)})"
        else:
            q = ""

        return f"Query({q})"

    __repr__ = __str__


Q = Query


###################################################
## Helper Utils
###################################################
SQL_DEBUG = os.environ.get("JSONLiteDB_SQL_DEBUG", "false").lower() == "true"
if SQL_DEBUG:  # pragma: no cover

    def sqldebug(sql):
        sqllogger.debug(dedent(sql))

else:

    def sqldebug(sql):
        pass


_about_obj = namedtuple("About", ("created", "version"))


def _query_tuple2jsonpath(*args, **kwargs):
    """Helper tool to build arguments. See query() method for details"""

    kw = {}
    for arg in args:
        if not isinstance(arg, dict):
            arg = {arg: None}
        kw |= arg

    kwargs = kw | kwargs
    updated = {}
    for key, val in kwargs.items():
        if isinstance(key, str):  # Single
            if key.startswith("$"):  # Already done!
                updated[key] = val
            else:
                updated[f'$."{key}"'] = val  # quote it
            continue

        if isinstance(key, int):
            updated[f"$[{key:d}]"] = val
            continue

        # Nested
        if not isinstance(key, tuple):
            raise ValueError(f"Unsuported key type for: {key!r}")

        # Need to combine but allow for integers including the first one
        key = group_ints_with_preceding_string(key)
        if key and isinstance(key[0][0], int):
            newkey = ["$" + "".join(f"[{i:d}]" for i in key[0])]
            del key[0]
        else:
            newkey = ["$"]

        for keygroup in key:
            skey, *ints = keygroup
            newkey.append(f'"{skey}"' + "".join(f"[{i:d}]" for i in ints))
        updated[".".join(newkey)] = val

    return updated


class AssignedQueryError(ValueError):
    pass


def build_index_paths(*args):
    """
    Turn strings, tuple of strings, or query objects into the JSON path.

        build_index_paths('key') --> ['$."key"']

        build_index_paths('key1','key2') --> ['$."key1"', '$."key2"']

        build_index_paths(('key1','key2')) --> ['$."key1"."key2"']
        build_index_paths(db.Q.key1.key2) --> ['$."key1"."key2"']

    Multiple items are joined. That is
        build_index_paths('key1','key2') == [
            build_index_paths('key1')[0],
            build_index_paths('key2')[0]
        ]
    """

    paths = []

    # Arguments. w/ or w/o values
    for arg in args:
        if isinstance(arg, dict):
            raise AssignedQueryError("Cannot index query dict. Just use the path(s)")
        if isinstance(arg, Query):
            if arg._query:
                raise AssignedQueryError(
                    "Cannot index an assigned query. "
                    "Example: 'db.Q.key' is acceptable "
                    "but 'db.Q.key == val' is NOT"
                )
            arg = tuple(arg._key)
        arg = _query_tuple2jsonpath(arg)  # Now it is a len-1 dict. Just use the key
        path = list(arg)[0]
        paths.append(path)

    # This removes equality but it really shouldn't be there for path building
    # paths.extend(_query_tuple2jsonpath(kwargs).keys())
    return paths


def build_orderby_pairs(orderby):
    """
    Turns orderby (JSON Path, ORDER) pairs
    """
    if not orderby:
        return ""

    if not isinstance(orderby, list):
        orderby = [orderby]

    orders = []
    for item in orderby:
        order = "ASC"

        # Handle type 4 first because will turn it unto a type 3. Set 'order' here
        # since type 3 only resets it if there is a + or -
        if isinstance(item, Query):
            if item._query:
                raise AssignedQueryError(
                    "Cannot index an assigned query. Example: 'db.Q.key' is acceptable "
                    "but 'db.Q.key == val' is NOT"
                )
            order = item._asc_or_desc or order  # default to ASC
            item = tuple(item._key)

        if isinstance(item, str):  # type 1 or 2
            if item.startswith("-"):
                order = "DESC"
                item = item[1:]
            elif item.startswith("+"):
                item = item[1:]

            if not item.startswith("$"):
                item = f'$."{item}"'
            orders.append((item, order))

        elif isinstance(item, tuple):  # type 3
            if len(item) == 0:
                raise ValueError("Cannot have an empty tuple for ordering")

            if isinstance(item[0], str):
                if item[0].startswith("-"):
                    order = "DESC"
                    item = (item[0][1:], *item[1:])
                elif item[0].startswith("+"):
                    item = (item[0][1:], *item[1:])

            item = group_ints_with_preceding_string(item)
            if item and isinstance(item[0][0], int):
                newitem = ["$" + "".join(f"[{i:d}]" for i in item[0])]
                del item[0]
            else:
                newitem = ["$"]

            for itemgroup in item:
                sitem, *ints = itemgroup
                newitem.append(f'"{sitem}"' + "".join(f"[{i:d}]" for i in ints))

            orders.append((".".join(newitem), order))
        else:
            raise ValueError("Unrecognized item for ORDER BY")
    return orders


def split_query(path):
    """
    This is the reverse of query_args and _build_index_paths.
    Splits a full JSON path into parts
    """
    if not path:
        return tuple()
    # Combine and then split it to be certain of the format
    path = build_index_paths(path)[0]  # returns full path

    path = split_no_double_quotes(path, ".")

    # Now need to handle tuples
    new_path = []
    if path[0].startswith("$["):  # Q()[#]
        new_path.append(int(path[0][2:-1]))
    for item in path[1:]:  # skip first since it is $
        item, *ixs = item.split("[")

        # Remove quotes from item and save it
        new_path.append(item.strip('"'))

        # Add index
        for ix in ixs:
            ix = ix.removesuffix("]")
            ix = int(ix)
            new_path.append(ix)

    return tuple(new_path)


###################################################
## General Utils
###################################################
class Row(sqlite3.Row):
    """
    Extended SQLite row with dictionary-like helpers.

    This class subclasses :class:`sqlite3.Row` to provide convenience
    methods commonly found on dictionaries, such as ``items()``,
    ``values()``, and ``get()``, while preserving the performance and
    memory characteristics of SQLite's native row object.

    Notes
    -----
    - Column access is performed via ``self[key]`` and remains backed by
      the underlying SQLite row representation.
    - Conversion to a Python ``dict`` is performed only when explicitly
      requested via ``todict()``.
    - A subtle incompatibility exists with PyPy's handling of
      ``sqlite3.Row``. In this codebase, it is only exercised in unit
      tests and does not affect runtime usage.

    Methods
    -------
    todict()
        Return the row as a dictionary mapping column names to values.
    items()
        Yield ``(key, value)`` pairs for each column.
    values()
        Yield values for each column.
    get(key, default=None)
        Return the value for `key` if present, otherwise `default`.
    """

    def todict(self):
        return {k: self[k] for k in self.keys()}

    def values(self):
        for k in self.keys():
            yield self[k]

    def items(self):
        for k in self.keys():
            yield k, self[k]

    def get(self, key, default=None):
        try:
            return self[key]
        except Exception:
            return default

    def __str__(self):
        return "Row(" + str(self.todict()) + ")"

    __repr__ = __str__


def listify(items, expand_tuples=True):
    """
    Normalize an input value into a list.

    The input may be a list, a string, or an iterable. If `items` is
    ``None`` or evaluates to ``False``, an empty list is returned. A
    string is treated as a single item and wrapped in a list rather than
    iterated character-by-character.

    Parameters
    ----------
    items : list, str, iterable, or None
        Value to be converted into a list.

    expand_tuples : bool, optional (default True)
        Whether to `list(items)` if `items` is a tuple

    Returns
    -------
    list
        A list representation of `items`.

    Notes
    -----
    - If `items` is already a list, it is returned unchanged.
    - If `items` is a string, it is wrapped in a one-element list.
    - If `items` is ``None`` or evaluates to ``False``, an empty list is
      returned.
    - Other iterables are converted using ``list(items)``.

    Examples
    --------
    >>> listify(None)
    []

    >>> listify("a")
    ['a']

    >>> listify(("a", "b"))
    ['a', 'b']

    >>> listify([])
    []
    """
    if isinstance(items, list):
        return items

    items = items or []

    if isinstance(items, str):
        items = [items]

    if isinstance(items, tuple) and not expand_tuples:
        items = [items]

    return list(items)


def group_ints_with_preceding_string(seq):
    """
    Group integers with the immediately preceding string.

    The input sequence must contain only strings and integers. Each string
    starts a new group, and any immediately following integers are included
    in that group. Leading integers (those appearing before any string) form
    their own group.

    Parameters
    ----------
    seq : sequence of (str or int)
        Input sequence containing only strings and integers.

    Returns
    -------
    list of list
        Grouped sequence where integers are associated with the most recent
        preceding string.

    Notes
    -----
    - Boolean values are not supported and must not appear in `seq`.
    - The function does not attempt to coerce or validate types beyond
      assuming the input contains only `str` and `int`.
    - Leading integers are allowed and will be grouped together until the
      first string is encountered.

    Examples
    --------
    >>> group_ints_with_preceding_string(['A', 'B', 'C'])
    [['A'], ['B'], ['C']]

    >>> group_ints_with_preceding_string(['A', 1, 'B', 2, 3, 'C'])
    [['A', 1], ['B', 2, 3], ['C']]

    >>> group_ints_with_preceding_string([1, 2, 'A', 'B', 3])
    [[1, 2], ['A'], ['B', 3]]
    """
    groups = []
    group = []

    for item in seq:
        if isinstance(item, int) and not isinstance(item, bool):
            group.append(item)
        else:
            if group:
                groups.append(group)
            group = [item]

    if group:
        groups.append(group)

    return groups


def sqlite_quote(text):
    """
    Return a SQLite-escaped SQL literal for a string.

    This function delegates string quoting and escaping to SQLite itself
    by executing a parameterized query and capturing the resulting SQL
    via a trace callback. The returned value is a SQL literal suitable
    for direct embedding in SQLite statements.

    Parameters
    ----------
    text : str
        Input string to be quoted for safe inclusion in SQLite SQL.

    Returns
    -------
    str
        SQLite-escaped SQL literal representing `text`, including
        surrounding quotes.

    Notes
    -----
    This function exists as a workaround for SQLite contexts where
    parameter substitution is not supported (e.g., `JSON_EXTRACT`
    and certain expressions). When parameter binding is available,
    it should always be preferred.

    Internally, the function:
    - Creates an in-memory SQLite database
    - Executes a parameterized `SELECT ?` query
    - Captures the executed SQL via `set_trace_callback`
    - Extracts the quoted literal emitted by SQLite

    The overhead of this approach is approximately 15 microseconds per
    call and is considered acceptable for correctness and safety.

    This relies on SQLite implementation details and should be treated
    as a pragmatic but non-idiomatic solution.
    """
    quoted = io.StringIO()

    tempdb = sqlite3.connect(":memory:")
    tempdb.set_trace_callback(quoted.write)
    tempdb.execute("SELECT\n?", (text,))

    quoted = "\n".join(quoted.getvalue().splitlines()[1:])  # Allow for new lines
    return quoted


def split_no_double_quotes(s, delimiter):
    """
    Splits 's' at 'delimiter' but ignores items in double quotes
    """
    quoted = re.findall(r"(\".*?\")", s)
    reps = {q: randstr() for q in quoted}  # Could have harmless repeats
    ireps = {v: k for k, v in reps.items()}

    s = translate(s, reps)
    s = s.split(delimiter)
    return [translate(t, ireps) for t in s]


def randstr(N=16):
    """
    Generate a random URL-safe Base64-encoded string.

    Parameters
    ----------
    N : int, optional
        Number of random bytes to generate before Base64 encoding.
        Default is 16.

    Returns
    -------
    str
        URL-safe Base64-encoded string generated from `N` random bytes.
        The output length is approximately ``4/3 * N`` characters and
        depends on the amount of padding removed during encoding.

    Notes
    -----
    The function uses :func:`os.urandom` to generate cryptographically
    secure random bytes. The bytes are encoded using URL-safe Base64
    encoding and any trailing ``'='`` padding characters are removed,
    so the resulting string length is not necessarily a multiple of 4.
    """
    rb = os.urandom(N)
    return base64.urlsafe_b64encode(rb).rstrip(b"=").decode("ascii")


def randkey(N=16):
    return f"!>>{randstr(N=N)}<<!"


def translate(mystr, reps):
    for key, val in reps.items():
        mystr = mystr.replace(key, str(val))
    return mystr


###################################################
## CLI Utils
###################################################
def cli():
    import argparse
    from textwrap import dedent

    desc = dedent(
        """
        Command line tool for adding JSONL to a JSONLiteDB (sqlite) file.
        
        stdin is assumed to be line-delimited or can handle if there is just one entry
        per line.
        """
    )

    parser = argparse.ArgumentParser(description=desc)

    global_parent = argparse.ArgumentParser(add_help=False)
    global_parent.add_argument(
        "--table",
        default="items",
        metavar="NAME",
        help="Table Name. Default: '%(default)s'",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s-" + __version__,
    )
    subparser = parser.add_subparsers(
        dest="command",
        title="Commands",
        required=True,
        # metavar="",
        description="Run `%(prog)s <command> -h` for help",
    )

    load = subparser.add_parser(
        "insert",
        parents=[global_parent],
        help="insert JSON into a database",
    )

    load.add_argument(
        "--duplicates",
        choices={"replace", "ignore"},
        default=False,
        help='How to handle errors if there are any "UNIQUE" constraints',
    )

    load.add_argument("dbpath", help="JSONLiteDB file")
    load.add_argument(
        "file",
        nargs="*",
        default=["-"],
        help="""
            Specify one or more JSON(L) files. If ends in '.jsonl', it will assume
            it is line-delimited JSON (or one-entry-per-line). If '.json', will read
            entire file. If '-' is specified (default), will read stdin. Will append in
            order
            """,
    )

    dump = subparser.add_parser(
        "dump",
        help="dump database to JSONL",
        parents=[global_parent],
        description="Dump the ",
    )

    dump.add_argument("dbpath", help="JSONLiteDB file")

    dump.add_argument(
        "--output",
        default="-",
        help="""
            Specify output for dump. If '-' is specified (default), will write to
            stdout
            """,
    )
    dump.add_argument(
        "--file-mode",
        choices=("a", "w"),
        default="w",
        dest="mode",
        help="File mode for --output",
    )

    dump.add_argument(
        "--sql",
        action="store_true",
        help="""
            Do a full SQL dump, including all tables, indices, etc. 
            This is similar to .dump in the sqlite3 shell""",
    )

    args = parser.parse_args()
    db = JSONLiteDB(args.dbpath, table=args.table)

    if args.command == "insert":
        read_stdin = False
        for file in args.file:
            if file.lower().endswith(".json"):
                with open(file, "rt") as fp:
                    db.insertmany(json.load(fp), duplicates=args.duplicates)
                continue

            # Try to avoid loading the whole thing
            is_file = True
            if file == "-":
                if read_stdin:
                    continue
                is_file = False
                read_stdin = True
                fp = sys.stdin
            else:
                fp = open(file, "rt")

            try:
                # Do this as a series of generators so we can use insertmany for
                # better performance
                lines = (line.strip() for line in fp)
                lines = (line for line in lines if line not in "[]")
                lines = (line.rstrip(",") for line in lines)
                db.insertmany(lines, _dump=False, duplicates=args.duplicates)
            finally:
                if is_file:
                    fp.close()
    elif args.command == "dump":
        try:
            fp = (
                open(args.output, mode=f"{args.mode}t")
                if args.output != "-"
                else sys.stdout
            )
            if args.sql:
                for line in db.db.iterdump():
                    fp.write(line + "\n")
            else:
                for line in db.items(_load=False):
                    fp.write(line + "\n")
        finally:
            fp.close()

    db.close()


if __name__ == "__main__":  # pragma: no cover
    cli()
