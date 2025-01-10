#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import hashlib
import io
import json
import logging
import os
import random
import re
import sqlite3
import string
import sys
from collections.abc import MutableMapping
from functools import partialmethod
from textwrap import dedent

logger = logging.getLogger(__name__)
sqllogger = logging.getLogger(__name__ + "-sql")

__version__ = "0.1.4"

__all__ = ["JSONLiteDB", "Q", "Query", "sqlite_quote", "Row"]

if sys.version_info < (3, 8):  # pragma: no cover
    raise ImportError("Must use Python >= 3.8")

DEFAULT_TABLE = "items"


class JSONLiteDB:
    """
    JSON(Lines) SQLite Database. Simple SQLite3 backed JSON-based document database
    with powerful queries and indexing.

    Initialize a JSONLiteDB instance.

    Parameters:
    -----------
    dbpath : str
        Path to the SQLite database file. Use ':memory:' for an in-memory database.

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

        Returns:
        --------
        QueryResult
            An iterator of DBDicts, each representing a JSON object in the database.

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

          - String starting with "$" and follows SQLite's JSON path. Must properly quote
            if it has dots, etc. No additional quoting is performed

            >>> {"$.key":'val'}            # Single key
            >>> {"$.key.subkey":'val'}     # Nested keys
            >>> {"$.key.subkey[3]":'val'}  # Nested keys to nested list.

          - Tuple string-keys or integer items. The quoteing will be handled for you!

            >>> {('key',): 'val'}
            >>> {('key','subkey'): 'val'}
            >>> {('key','subkey',3): 'val'}

          - Advanced queries via query objects (explained below)

        Advanced queries allow for more comparisons. Note: You must be careful
        about parentheses for operations. Keys are assigned with attributes (dot)
        and/or items (brackets). Items can have multiple separated by a comma and
        can include integers for items within a list.

          >>> db.query(db.Q.key == val)
          >>> db.query(db.Q['key'] == val)

          >>> db.query(db.Q.key.subkey == val)
          >>> db.query(db.Q['key'].subkey == val)
          >>> db.query(db.Q.key.['subkey'] == val)
          >>> db.query(db.Q['key','subkey'] == val)

          >>> qb.query(db.Q.key.subkey[3] == val)

        Complex Example:
          >>> db.query((db.Q['other key',9] >= 4) & (Q().key < 3)) # inequality

        Queries support most comparison operations (==, !=, >,>=,<, <=, etc) plus:

            LIKE statements:  db.Q.key % "pat%tern"
            GLOB statements:  db.Q.key * "glob*pattern"
            REGEX statements: db.Q.key @ "regular.*expressions" (using Python's re)

        db.query() is also aliased to db() and db.search()
        """
        _load = query_kwargs.pop("_load", True)
        _1 = query_kwargs.pop("_1", False)  # private

        qstr, qvals = JSONLiteDB._query2sql(*query_args, **query_kwargs)
        res = self.execute(
            f"""
            SELECT rowid, data FROM {self.table} 
            WHERE
                {qstr}
            {"LIMIT 1" if _1 else ""}
            """,
            qvals,
        )

        return QueryResult(res, _load=_load)

    __call__ = search = query

    def query_one(self, *query_args, **query_kwargs):
        """
        Query the database and return a single item matching the criteria.

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
        DBDict or None
            A single DBDict object representing the JSON item, or None if no match is
            found.

        Examples:
        ---------
        >>> db.query_one(first='John', last='Lennon')

        See Also:
        ---------
        query : Method for querying multiple items.
        """
        query_kwargs["_1"] = True
        try:
            return next(self.query(*query_args, **query_kwargs))
        except StopIteration:
            return None

    search_one = one = query_one

    def count(self, *query_args, **query_kwargs):
        """
        Count the number of items matching the query criteria.

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

    def query_by_path_exists(self, path, _load=True):
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
            SELECT {function}(JSON_EXTRACT({self.table}.data, {sqlite_quote(path)})) AS val
            FROM {self.table}
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
        qstr, qvals = JSONLiteDB._query2sql(*query_args, **query_kwargs)

        res = self.execute(
            f"""
            EXPLAIN QUERY PLAN
            SELECT data FROM {self.table} 
            WHERE
                {qstr}
            """,
            qvals,
        )
        return [dict(row) for row in res]

    def remove(self, *query_args, **query_kwargs):
        """
        Remove items from the database matching the specified query criteria.
        WARNING: Not specifying any queries will purge the database.

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
        if isinstance(rowid, tuple):
            raise TypeError("Can only delete one item at a time. Try delete()")
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

        Returns:
        --------
        DBDict or None
            The item as a DBDict if found, or None if no item exists with the specified rowid.

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
        if isinstance(rowid, tuple):
            raise TypeError("Can only get one item at a time")
        return self.get_by_rowid(rowid)

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
        >>> db.insertmany([{'first': 'John', 'last': 'Lennon'}, {'first': 'Paul', 'last': 'McCartney'}])
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
        Update an existing item in the database.

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
        Apply a patch to all items matching the specified query criteria.

        Parameters:
        -----------
        patchitem : dict
            The patch to apply. Follows the RFC-7396 MergePatch algorithm.
            Note: Setting a key's value to None removes that key from the object.

        *query_args : positional arguments
            Arguments can be dictionaries of equality key:value pairs or advanced
            queries. Multiple are combined with AND logic.

        **query_kwargs : keyword arguments
            Keywords that represent equality conditions. Multiple are combined with
            AND logic.

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
        the value to None. This is an SQLite limitation. If this is needed, use a Python
        loop.

        References:
        -----------
        [1]: https://www.sqlite.org/json1.html#jpatch
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
                [patchitem, *qvals],
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
            Paths for which the index was created. Can be strings, tuples, or query objects.

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
            [self.table],
        )
        indres = {}
        for row in res:
            keys = re.findall(r"JSON_EXTRACT\(data,\s?'(.*?)'\s?\)", row["sql"])
            if not keys:
                continue
            indres[row["name"]] = keys
        return indres

    indices = indexes

    def _init(self, wal_mode=True):
        db = self.db
        try:
            with db:
                r = db.execute(
                    f"""
                    SELECT * FROM {self.table}_kv 
                    WHERE key = ? OR key = ?
                    ORDER BY key""",
                    ("created", "version"),
                ).fetchall()
                if len(r) == 2:  # Note it is ORDER BY so the order wont change
                    created, version = [i["val"] for i in r]
                    logger.debug(f"{created = } {version = }")
                    return
        except:
            logger.debug("DB does not exists. Creating")

        with self:
            db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table}(
                    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                    data JSON
                )"""
            )
            db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table}_kv(
                    key TEXT PRIMARY KEY,
                    val BLOB
                )"""
            )
            db.execute(
                f"""
                INSERT OR IGNORE INTO {self.table}_kv VALUES (?,?)
                """,
                ("created", datetime.datetime.now().astimezone().isoformat()),
            )
            db.execute(
                f"""
                INSERT OR IGNORE INTO {self.table}_kv VALUES (?,?)
                """,
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

        # Neet to replace all placeholders with '?' but we also need to do it in the proper order
        reQ = re.compile(r"(!>>.*?<<!)")
        qvals = reQ.findall(qobj._query)
        qvals = [qobj._qdict[k] for k in qvals]
        qstr = reQ.sub("?", qobj._query)
        return qstr, qvals

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
        [1]
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
def sqldebug(sql):  # pragma: no cover
    # This is really only used in devel.
    if os.environ.get("JSONLiteDB_SQL_DEBUG", "false").lower() == "true":
        sqllogger.debug(dedent(sql))


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
        key = group_ints_with_preceeding_string(key)
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


def build_index_paths(*args, **kwargs):
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

    paths.extend(_query_tuple2jsonpath(kwargs).keys())
    return paths


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
    Fancier but performant sqlite3 row. Note that there is a subtle incompatibility
    with this in PyPy. For JSONLiteDB, that is only exploited in unit tests and not
    elsewhere so this continues to work just fine. See the unit test of this code
    for details.
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
        except:
            return default

    def __str__(self):
        return "Row(" + str(self.todict()) + ")"

    __repr__ = __str__


def listify(flags):
    """Turn argument into a list. None or False-like become empty list"""
    if isinstance(flags, list):
        return flags
    flags = flags or []
    if isinstance(flags, str):
        flags = [flags]
    return list(flags)


def group_ints_with_preceeding_string(seq):
    """
    Group a seq into list of items where any following integers are also grouped.
    Includes support for initial
        ['A','B','C'] | [['A'], ['B'], ['C']] # Nothing
        ['A',1,'B',2,3,'C'] | [['A', 1], ['B', 2, 3], ['C']]
        [1,2,'A','B',3] | [[1, 2], ['A'], ['B', 3]]

    """
    newseq = []

    group = []
    for item in seq:
        if isinstance(item, int):
            group.append(item)
        else:
            if group:
                newseq.append(group)
            group = [item]

    # Add the last group if any
    if group:
        newseq.append(group)

    return newseq


def sqlite_quote(text):
    """A bit of a hack get sqlite escaped text"""
    # You could do this with just a replace and add quotes but I worry I may
    # miss something so use sqlite's directly to be sure. And this whole process
    # is about 15.6 µs ± 101 ns last time I profiled. Not worth improving further.
    #
    # Note: It is still better to use paramater substitution whenever possible. But
    #       sqlite doesn't support them in JSON_EXTRACT and other functions so it
    #       gets quoted for safety.
    quoted = io.StringIO()
    tempdb = sqlite3.connect(":memory:")
    tempdb.set_trace_callback(quoted.write)
    tempdb.execute("SELECT\n?", (text,))
    quoted = quoted.getvalue().splitlines()[1]
    return quoted


def split_no_double_quotes(s, delimiter):
    """
    Splits 's' at 'delimiter' but ignores items in double quotes
    """
    quoted = re.findall(r"(\".*?\")", s)
    reps = {q: randstr(10) for q in quoted}  # Repeats are fine!
    ireps = {v: k for k, v in reps.items()}

    s = translate(s, reps)
    s = s.split(delimiter)
    return [translate(t, ireps) for t in s]


def randstr(N=5):
    c = string.ascii_letters + string.digits
    return "".join(random.choice(c) for _ in range(N))


def randkey(N=5):
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

    parser.add_argument(
        "--table", default="items", metavar="NAME", help="['%(default)s'] Table Name"
    )

    parser.add_argument(
        "-v", "--version", action="version", version="%(prog)s-" + __version__
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
