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

__version__ = "0.1.10"

__all__ = ["JSONLiteDB", "Q", "Query", "sqlite_quote", "Row"]

if sys.version_info < (3, 8):  # pragma: no cover
    raise ImportError("Must use Python >= 3.8")

DEFAULT_TABLE = "items"


class JSONLiteDB:
    """
    SQLite-backed JSON document store with indexing and query helpers.

    JSONLiteDB stores documents as JSON in a single SQLite table (JSON1).
    It provides a compact API for insertion, queries, and indexing without
    loading the entire database into memory.

    Parameters
    ----------
    dbpath : str | Path | sqlite3.Connection
        Path to the SQLite file. Use ':memory:' for an in-memory database.
        If an existing sqlite3.Connection is provided, it is used directly
        and any sqlite3 connection kwargs are ignored.
    wal_mode : bool, optional
        Enable write-ahead logging. Defaults to True. You may also set
        WAL mode manually using `execute()` if you need finer control.
    table : str, optional
        Table name to store documents. Defaults to 'items'. The name is
        sanitized to alphanumerics and underscores.
    **sqlitekws : keyword arguments
        Extra keyword arguments passed to `sqlite3.connect`.

    Raises
    ------
    sqlite3.Error
        If SQLite cannot open the database.

    Examples
    --------
    >>> db = JSONLiteDB(":memory:")
    >>> db = JSONLiteDB("my/database.db", table="Beatles")
    >>> db = JSONLiteDB("data.db", check_same_thread=False)

    References
    ----------
    https://docs.python.org/3/library/sqlite3.html#module-functions
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
        Shortcut for `JSONLiteDB(...)`.

        Parameters
        ----------
        *args, **kwargs
            Passed through to `__init__`.

        Returns
        -------
        JSONLiteDB
            New database instance.
        """
        return cls(*args, **kwargs)

    open = connect

    @classmethod
    def read_only(cls, dbpath, **kwargs):
        """
        Open a database in read-only mode.

        Equivalent to:
        `JSONLiteDB(f"file:{dbpath}?mode=ro", uri=True, **kwargs)`.

        Parameters
        ----------
        dbpath : str
            SQLite database path.
        **kwargs : dict
            JSONLiteDB and sqlite3 keyword arguments.

        Returns
        -------
        JSONLiteDB
            Read-only database instance.
        """
        dbpath = f"file:{dbpath}?mode=ro"
        kwargs["uri"] = True
        return cls(dbpath, **kwargs)

    @classmethod
    def memory(cls, **kwargs):
        """
        Create an in-memory database.

        Equivalent to `JSONLiteDB(":memory:", **kwargs)`.
        """
        return cls(":memory:", **kwargs)

    def insert(self, *items, duplicates=False, _dump=True):
        """
        Insert one or more JSON documents.

        Parameters
        ----------
        *items : dict | str
            Documents to insert. Use dict/list objects by default, or pass JSON
            strings with `_dump=False`.
        duplicates : bool | str, optional
            How to handle unique index conflicts:
            - False (default): raise an error on duplicates.
            - True or "replace": replace existing rows.
            - "ignore": skip rows that violate uniqueness.
        _dump : bool, optional
            If True (default), JSON-encode items before insert.

        Raises
        ------
        ValueError
            If `duplicates` is not in {True, False, "replace", "ignore"}.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"first": "John", "last": "Lennon"})
        >>> db.insert({"first": "Paul"}, duplicates="ignore")

        See Also
        --------
        insertmany
        """
        return self.insertmany(items, duplicates=duplicates, _dump=_dump)

    add = insert

    def insertmany(self, items, duplicates=False, _dump=True):
        """
        Insert an iterable of documents.

        Parameters
        ----------
        items : iterable
            Documents to insert (dicts/lists) or JSON strings if `_dump=False`.
        duplicates : bool | str, optional
            Duplicate handling for unique indexes: False, True/"replace", or "ignore".
        _dump : bool, optional
            JSON-encode items when True (default).

        Raises
        ------
        ValueError
            If `duplicates` is not in {True, False, "replace", "ignore"}.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> items = [{"first": "John"}, {"first": "Paul"}]
        >>> db.insertmany(items, duplicates="ignore")
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
        Query documents matching one or more criteria.

        Parameters
        ----------
        *query_args : dict | Query
            Equality dictionaries or advanced Query objects. Multiple arguments
            are combined with AND logic.
        **query_kwargs : dict
            Equality constraints expressed as keyword arguments.

        Other Parameters
        ----------------
        _load : bool, optional
            If True (default), return decoded JSON (DBDict/DBList). If False,
            return raw JSON strings.
        _limit : int, optional
            Add `LIMIT N` to the SQL query. The return type is still an iterator.
        _orderby : str | tuple | Query | list, optional
            Order-by specification. See "Order By" below.

        Returns
        -------
        QueryResult
            Iterator over matching rows. Each row is a DBDict/DBList with a
            `rowid` attribute when `_load=True`.

        Examples
        --------
        >>> db.query(first="John", last="Lennon")
        >>> db.query({"birthdate": 1940})
        >>> db.query((db.Q.first == "Paul") | (db.Q.first == "John"))
        >>> db.query((db.Q.first % "Geo%") & (db.Q.birthdate <= 1943))

        Query Forms
        -----------
        Keyword equality:
        >>> db.query(key=val)
        >>> db.query(key1=val1, key2=val2)  # AND

        Equality dictionaries:
        >>> db.query({"key": val})
        >>> db.query({"key1": val1, "key2": val2})  # AND
        >>> db.query({"key1": val1}, {"key2": val2})  # AND

        Nested keys via JSON path or tuples:
        >>> {"$.key": "val"}
        >>> {"$.key.subkey[3]": "val"}
        >>> {("key", "subkey"): "val"}
        >>> {("key", "subkey", 3): "val"}

        Advanced Query objects:
        >>> db.query(db.Q.key == val)
        >>> db.query(db.Q["key"] == val)
        >>> db.query(db.Q.key.subkey == val)
        >>> db.query(db.Q["key", "subkey"] == val)
        >>> db.query(db.Q.key.subkey[3] == val)

        Complex example:
        >>> db.query((db.Q["other key", 9] >= 4) & (Q().key < 3))

        Operators supported: ==, !=, >, >=, <, <= plus:
        - LIKE:  `db.Q.key % "pat%tern"`
        - GLOB:  `db.Q.key * "glob*pattern"`
        - REGEXP: `db.Q.key @ "regex.*"` (Python `re`)

        Notes
        -----
        - REGEXP uses Python's `re` and is often slower than LIKE/GLOB.
        - Index usage depends on JSON path form. `$.key.subkey` is not the
          same as `("key", "subkey")` for index matching.
        - `db.query` is also available as `db()` and `db.search()`.

        Order By
        --------
        Use `_orderby` to specify ordering. Accepted forms:
        1) JSON path string:
           >>> "$.key"
           >>> "-$.key.subkey"
        2) Plain key name (auto-quoted):
           >>> "key"
           >>> "-key"
        3) Tuple path (first element can include +/-):
           >>> ("key", "subkey")
           >>> ("-key", "subkey", 3)
        4) Query object (no comparison):
           >>> db.Q.key
           >>> -db.Q.key.subkey

        Multiple orderings:
        >>> ["-key1", db.Q.key2, ("-key3", "subkey")]

        A leading `-` selects DESC, `+` selects ASC (default).
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
        Return the first matching document (or None).

        This is equivalent to `query(..., _limit=1)` but returns a single
        item or None instead of an iterator.

        Parameters
        ----------
        *query_args, **query_kwargs
            Same as `query()`.

        Returns
        -------
        DBDict | DBList | object | None
            Decoded JSON object, list, scalar, or None if no match.

        Examples
        --------
        >>> db.query_one(first="John", last="Lennon")

        See Also
        --------
        query
        """
        query_kwargs["_limit"] = 1
        try:
            return next(self.query(*query_args, **query_kwargs))
        except StopIteration:
            return None

    search_one = one = query_one
    find_one = query_one

    def count(self, *query_args, **query_kwargs):
        """
        Count matching documents using SQLite.

        Parameters
        ----------
        *query_args, **query_kwargs
            Same as `query()`.

        Returns
        -------
        int
            Number of matching rows.

        Examples
        --------
        >>> db.count(first="George")
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
        Return documents that contain a given JSON path.

        This differs from `db.query(db.Q.path != None)` because it matches
        paths that exist even if the stored value is `None`.

        Parameters
        ----------
        path : str | tuple | Query
            JSON path to check for existence.
        _load : bool, optional
            Load JSON objects (default True).
        _orderby : optional
            Ordering specification. See `query()`.

        Returns
        -------
        QueryResult
            Iterator over rows where the path exists.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"first": "John", "details": {"birthdate": 1940}})
        >>> list(db.query_by_path_exists(("details", "birthdate")))
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

    def count_by_path_exists(self, path):
        """
        Count documents where a JSON path exists.

        Parameters
        ----------
        path : str | tuple | Query
            JSON path to check for existence.

        Returns
        -------
        int
            Number of rows where the path exists.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"a": {"b": 1}})
        >>> db.count_by_path_exists(("a", "b"))
        1
        """
        path = split_query(path)
        if len(path) == 0:
            return 0
        if len(path) == 1:
            parent = Query()
            child = path[0]
        else:
            parent = path[:-1]
            child = path[-1]

        parent = build_index_paths(parent)[0]

        res = self.execute(
            f"""
            SELECT COUNT(DISTINCT {self.table}.rowid) as count
            FROM
                {self.table},
                JSON_EACH({self.table}.data,?) as each
            WHERE
                each.key = ?
            """,
            (parent, child),
        ).fetchone()
        return res["count"]

    def aggregate(self, path, /, function):
        """
        Compute an aggregate over a JSON path.

        Parameters
        ----------
        path : str | tuple | Query
            JSON path to aggregate.
        function : str
            One of: 'AVG', 'COUNT', 'MAX', 'MIN', 'SUM', 'TOTAL'.

        Returns
        -------
        float | int
            Aggregate result.

        Raises
        ------
        ValueError
            If an unsupported aggregate function is provided.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insertmany([{"value": 10}, {"value": 20}, {"value": 30}])
        >>> db.aggregate("value", "AVG")
        20.0

        >>> db.AVG("value")
        20.0
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

    def explain_query(self, *query_args, **query_kwargs):
        """
        Return `EXPLAIN QUERY PLAN` rows for a query.

        Parameters
        ----------
        *query_args, **query_kwargs
            Same as `query()`.
        """
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

    analyze = explain_query

    def remove(self, *query_args, **query_kwargs):
        """
        Remove documents matching the query.

        WARNING: If no criteria are provided, all rows are deleted.

        Parameters
        ----------
        *query_args, **query_kwargs
            Same as `query()`.

        Examples
        --------
        >>> db.remove(first="George")
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
        Delete all documents in the table.

        Examples
        --------
        >>> db.purge()
        >>> len(db)
        0
        """
        self.remove()

    def remove_by_rowid(self, *rowids):
        """
        Remove documents by rowid.

        Parameters
        ----------
        *rowids : int
            One or more SQLite rowids.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"first": "Ringo", "last": "Starr"})
        >>> item = db.query_one(first="Ringo")
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
        Delete a single document by rowid.

        Parameters
        ----------
        rowid : int
            SQLite rowid to delete (rowids start at 1).

        Raises
        ------
        TypeError
            If `rowid` is a tuple. Use `remove_by_rowid()` for multiple rows.
        IndexError
            If no row exists with the given rowid.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"first": "George", "last": "Martin"})
        >>> del db[1]
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
        Retrieve a document by rowid.

        Parameters
        ----------
        rowid : int
            SQLite rowid to fetch.
        _load : bool, optional
            Return decoded JSON (default True) or raw JSON string.

        Returns
        -------
        DBDict | DBList | object | None
            Decoded JSON object/list, scalar, or None if not found.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"first": "George", "last": "Martin"})
        >>> item = db.query_one(first="George")
        >>> db.get_by_rowid(item.rowid)
        {'first': 'George', 'last': 'Martin'}
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
        Fetch a document by rowid (raises if missing).

        Parameters
        ----------
        rowid : int
            SQLite rowid to fetch.

        Returns
        -------
        DBDict | DBList | object
            Decoded JSON object/list or scalar.

        Raises
        ------
        TypeError
            If `rowid` is a tuple.
        IndexError
            If no row exists with the given rowid.

        See Also
        --------
        get_by_rowid
        """
        if isinstance(rowid, tuple):
            raise TypeError("Can only get one item at a time")
        item = self.get_by_rowid(rowid)
        if item is None:  # Explicit for None to avoid empty dict raising error
            raise IndexError(f"{rowid = } not found")
        return item

    def items(self, _load=True):
        """
        Iterate over all documents (unordered).

        Parameters
        ----------
        _load : bool, optional
            Return decoded JSON (default True) or raw JSON strings.

        Returns
        -------
        QueryResult
            Iterator over all rows.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insertmany([{"first": "John"}, {"first": "Paul"}])
        >>> list(db.items())
        """
        res = self.execute(f"SELECT rowid, data FROM {self.table}")

        return QueryResult(res, _load=_load)

    __iter__ = items

    def update(self, item, rowid=None, duplicates=False, _dump=True):
        """
        Replace a stored document by rowid.

        Parameters
        ----------
        item : dict | str
            Replacement document or JSON string if `_dump=False`.
        rowid : int, optional
            Rowid to update. If omitted, uses `item.rowid` if present.
        duplicates : bool | str, optional
            Handling for unique index conflicts (False, True/"replace", "ignore").
        _dump : bool, optional
            JSON-encode `item` when True (default).

        Raises
        ------
        MissingRowIDError
            If `rowid` is not provided and cannot be inferred.
        ValueError
            If `duplicates` is not in {True, False, "replace", "ignore"}.

        See Also
        --------
        patch

        Examples
        --------
        >>> db.update({"first": "George", "last": "Harrison"}, rowid=1)
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
        Apply an RFC-7396 JSON Merge Patch to matching documents.

        Parameters
        ----------
        patchitem : dict | str
            Merge Patch document. Setting a key to None removes that key.
        *query_args, **query_kwargs
            Selection criteria (same as `query()`). If omitted, all rows
            are patched.
        _dump : bool, optional
            JSON-encode `patchitem` when True (default).

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"first": "George", "role": "producer"})
        >>> db.patch({"role": "composer"}, first="George")
        >>> db.patch({"role": None}, first="George")  # delete key

        Notes
        -----
        - `None` removes keys, so you cannot set a value to JSON null
          via `patch()`. Use a Python loop if you need explicit nulls.

        References
        ----------
        https://www.sqlite.org/json1.html#jpatch
        https://datatracker.ietf.org/doc/html/rfc7396
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
        Count keys at a given JSON path across all documents.

        Parameters
        ----------
        start : str | tuple | Query | None, optional
            Root path to inspect. Defaults to the document root.

        Returns
        -------
        dict
            Mapping of key -> count.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insertmany(
        ...     [
        ...         {"first": "John", "address": {"city": "New York"}},
        ...         {"first": "Paul", "address": {"city": "Liverpool"}},
        ...         {"first": "George"},
        ...     ]
        ... )
        >>> db.path_counts()
        {'first': 3, 'address': 2}
        >>> db.path_counts("address")
        {'city': 2}
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
        Return keys present at a given JSON path.

        This is shorthand for `path_counts(start).keys()`.

        Parameters
        ----------
        start : str | tuple | Query | None, optional
            Path to inspect. Defaults to the root.

        Returns
        -------
        KeysView
            View of keys found at the specified path.
        """
        return self.path_counts(start=start).keys()

    def create_index(self, *paths, unique=False):
        """
        Create an index on one or more JSON paths.

        Parameters
        ----------
        *paths : str | tuple | Query
            Paths to index. Accepts the same path forms as `query()`.
        unique : bool, optional
            Create a UNIQUE index if True.

        Examples
        --------
        >>> db.create_index("first")
        >>> db.create_index("first", "last")
        >>> db.create_index(db.Q.first, db.Q.last)
        >>> db.create_index(("address", "city"))
        >>> db.create_index(db.Q.address.city)
        >>> db.create_index(db.Q.addresses[1])

        Notes
        -----
        SQLite index usage depends on the JSON path syntax. For example,
        `db.create_index("key")` and `db.create_index("$.key")` are not
        interchangeable for index matching. Use the same form in `query()`
        as you used when creating the index.
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
        Drop an index by name.

        Parameters
        ----------
        name : str
            Index name as returned by `indexes`.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.create_index("first", "last")
        >>> list(db.indexes)
        ['ix_items_...']
        >>> db.drop_index_by_name("ix_items_...")
        """
        with self:  # Apparently this also must be manually quoted
            self.execute(f"DROP INDEX IF EXISTS {sqlite_quote(name)}")

    def drop_index(self, *paths, unique=False):
        """
        Drop an index by path definition.

        Parameters
        ----------
        *paths : str | tuple | Query
            Paths used to create the index.
        unique : bool, optional
            Whether to target the UNIQUE index variant.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.create_index("first", "last", unique=True)
        >>> db.drop_index("first", "last")  # no-op
        >>> db.drop_index("first", "last", unique=True)
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
        """Return a mapping of index name -> list of JSON paths."""
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
        """Return metadata (created timestamp and version) from the kv table."""
        r = self.execute(
            f"""
                SELECT * FROM {self.table}_kv 
                WHERE key = ? OR key = ?
                ORDER BY key""",
            ("created", "version"),
        ).fetchall()
        # Note: ORDER BY keeps results stable for this query.
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
        Build SQL WHERE clause and bind values from query inputs.

        Returns a `(where_sql, values)` tuple suitable for parameterized
        execution. If no criteria are provided, returns `"1 = 1"`.
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

        # Need to replace all placeholders with '?' but we also need to do
        # it in the proper order. May move to named (dict) style in the future but
        # this works well enough.
        reQ = re.compile(r"(!>>.*?<<!)")
        qvals = reQ.findall(qobj._query)
        qvals = [qobj._qdict[k] for k in qvals]
        qstr = reQ.sub("?", qobj._query)
        return qstr, qvals

    def _orderby2sql(self, orderby):
        """
        Convert an `_orderby` specification into an SQL ORDER BY clause.
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
        Return the number of documents in the table.

        Examples
        --------
        >>> db = JSONLiteDB(":memory:")
        >>> db.insert({"first": "John"})
        >>> len(db)
        1
        """
        res = self.execute(f"SELECT COUNT(rowid) FROM {self.table}").fetchone()
        return res[0]

    def close(self):
        """
        Close the underlying SQLite connection.
        """
        logger.debug("close")
        self.db.close()

    __del__ = close

    def wal_checkpoint(self, mode=None):
        """
        Run a WAL checkpoint.

        Parameters
        ----------
        mode : str | None, optional
            One of: None, 'PASSIVE', 'FULL', 'RESTART', 'TRUNCATE'.

        References
        ----------
        https://sqlite.org/wal.html#ckpt
        """
        if not mode in {None, "PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError(f"Invalid {mode = } specified")
        mode = f"({mode})" if mode else ""
        try:
            with self:
                self.execute(f"PRAGMA wal_checkpoint{mode};")
        except sqlite3.DatabaseError as E:  # pragma: no cover
            logger.debug(f"WAL checkpoint error {E!r}")

    def execute(self, *args, **kwargs):
        """
        Execute a SQL statement on the underlying sqlite3 connection.

        Returns
        -------
        sqlite3.Cursor
        """
        return self.db.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        """
        Execute a parameterized SQL statement multiple times.

        Returns
        -------
        sqlite3.Cursor
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
    """Dictionary subclass that carries a `rowid` attribute."""


class DBList(list):
    """List subclass that carries a `rowid` attribute."""


class QueryResult:
    """
    Iterator wrapper for query results.

    Returns decoded JSON objects by default (DBDict/DBList with `rowid`).
    Use `_load=False` to iterate over raw JSON strings.
    """

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
    """SQLite REGEXP callback using Python's `re` module."""
    return bool(re.search(pattern, string))


class MissingValueError(ValueError):
    pass


class DissallowedError(ValueError):
    pass


class MissingRowIDError(ValueError):
    pass


class Query:
    """
    Build composable query expressions for JSONLiteDB.

    Use attribute access or indexing to build paths, then compare to create
    SQL fragments. Query objects can be combined with `&`, `|`, and `~`.
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
    """
    Normalize query inputs into JSON paths.

    Accepts dictionaries, strings, tuples, and integers and returns a mapping
    of JSON path strings to values. See `query()` for accepted forms.
    """

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
            raise ValueError(f"Unsupported key type for: {key!r}")

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
    Normalize paths for index creation.

    Examples
    --------
    >>> build_index_paths("key")
    ['$."key"']
    >>> build_index_paths("key1", "key2")
    ['$."key1"', '$."key2"']
    >>> build_index_paths(("key1", "key2"))
    ['$."key1"."key2"']
    >>> build_index_paths(db.Q.key1.key2)
    ['$."key1"."key2"']

    Multiple inputs are returned as separate paths.
    """

    paths = []

    # Arguments, with or without values.
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
    Normalize an order-by specification into (json_path, order) pairs.
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
    Split a JSON path into component keys/indices.

    This is the inverse of the path-building helpers used by `query()`.
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
    Split on a delimiter while preserving quoted substrings.
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
    """
    Return a unique placeholder token for SQL query assembly.
    """
    return f"!>>{randstr(N=N)}<<!"


def translate(mystr, reps):
    """
    Replace all keys in `reps` with their corresponding values in `mystr`.
    """
    for key, val in reps.items():
        mystr = mystr.replace(key, str(val))
    return mystr


###################################################
## CLI Utils
###################################################
def cli():
    """Entry point for the JSONLiteDB command-line interface."""
    import argparse
    from textwrap import dedent

    desc = dedent(
        """
        Command-line tool for inserting JSON/JSONL into a JSONLiteDB (SQLite) file.

        Input is treated as JSON Lines (one JSON value per line). Files ending in
        .json are parsed as full JSON; .jsonl files are read line-by-line.
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
            One or more JSON/JSONL files. Files ending in '.jsonl' are read line-by-line.
            Files ending in '.json' are parsed as full JSON. Use '-' to read stdin.
        """,
    )

    dump = subparser.add_parser(
        "dump",
        help="dump database to JSONL",
        parents=[global_parent],
        description="Dump a JSONLiteDB table to JSONL or full SQL.",
    )

    dump.add_argument("dbpath", help="JSONLiteDB file")

    dump.add_argument(
        "--output",
        default="-",
        help="""
            Output file path. Use '-' (default) to write to stdout.
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
            Emit a full SQL dump including tables and indexes (like `.dump` in
            the sqlite3 shell).
        """,
    )

    query = subparser.add_parser(
        "query",
        help="query database and emit JSONL",
        parents=[global_parent],
    )
    query.add_argument("dbpath", help="JSONLiteDB file")
    query.add_argument(
        "filters",
        nargs="*",
        help="Filters in key=value form (values parsed as JSON when possible)",
    )
    query.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Limit results to N rows",
    )
    query.add_argument(
        "--orderby",
        action="append",
        default=None,
        help=(
            "Order by key or JSON path; repeatable. Use commas to denote nested "
            "paths (e.g., --orderby name --orderby=-age --orderby=-parent,child)."
        ),
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
    elif args.command == "query":
        eq_args = []
        eq_kwargs = {}
        for filt in args.filters:
            if "=" not in filt:
                raise ValueError(f"Invalid filter {filt!r}. Use key=value.")
            key, val = filt.split("=", 1)
            key = key.strip()
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                pass

            if key.startswith("$"):
                eq_args.append({key: val})
            else:
                eq_kwargs[key] = val

        q_kwargs = {}
        if args.limit is not None:
            q_kwargs["_limit"] = args.limit
        if args.orderby:
            orderby = []
            for item in args.orderby:
                parts = [p.strip() for p in item.split(",") if p.strip()]
                if len(parts) > 1:
                    orderby.append(tuple(parts))
                else:
                    orderby.append(parts[0])
            q_kwargs["_orderby"] = orderby

        for line in db.query(*eq_args, _load=False, **eq_kwargs, **q_kwargs):
            sys.stdout.write(line + "\n")

    db.close()


if __name__ == "__main__":  # pragma: no cover
    cli()
