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

__version__ = "0.1.1"

__all__ = ["JSONLiteDB", "JSONLiteDBKeyValue", "Q", "Query", "sqlite_quote", "Row"]

if sys.version_info < (3, 8):  # pragma: no cover
    raise ImportError("Must use Python >= 3.8")

DEFAULT_TABLE = "items"


class JSONLiteDB:
    """
    JSON(Lines) SQLite Database. Simple SQLite3 backed JSON-based document database

    Inputs:
    -------
    dbpath
        String path representing the database. Can also be ':memory:'. If uri=True
        is passed, can be an SQLite URI path (including read-only flags)

    table [DEFAULT_TABLE == 'items']
        Table name

    **sqlitekws
        Passed to sqlite3.connect. Some useful examples:
            check_same_thread, uri

    """

    def __init__(
        self,
        /,
        dbpath,
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

        self._init()

    @classmethod
    def connect(cls, *args, **kwargs):
        """Shortcut for new. Same as __init__"""
        return cls(*args, **kwargs)

    open = connect

    @classmethod
    def read_only(cls, dbpath, **kwargs):
        """
        Shortcut For
            JSONLiteDB(f"file:{dbpath}?mode=ro",uri=True,**kwargs)
        where **kwargs can contain both JSONLiteDB and sqlite3 args
        """
        dbpath = f"file:{dbpath}?mode=ro"
        kwargs["uri"] = True
        return cls(dbpath, **kwargs)

    def insert(self, *items, duplicates=False, _dump=True):
        """
        Insert one or more items where each item is an argument.

        *items
            items to add. Each item is its own argument. Otherwise, see
            insertmany()

        duplicates [False] -- Options: False, True, "ignore", "replace"
            How to handle duplicate items IF AND ONLY IF there is a "unique" index.
            If there isn't a unique index, items will be added regardless!
                False     : Do nothing but a unique index will cause an error
                True      : Same as "replace"
                "replace" : Replace items that violate a unique index
                "ignore"  : ignore items that violate a unique index

        _dump [True]
            Converts items to JSON. Set to False if input is already JSON.

        See also: insertmany"""
        return self.insertmany(items, duplicates=duplicates, _dump=_dump)

    add = insert

    def insertmany(self, items, duplicates=False, _dump=True):
        """Insert a list of items. See insert() for help"""
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
            self.db.executemany(
                f"""
                INSERT {rtxt} INTO {self.table} (data)
                VALUES (JSON(?))
                """,
                ins,
            )

    def query(self, *query_args, **query_kwargs):
        """
        Query the database.

        Queries can take some of the following forms:
          Keyword:
            db.query(key=val)
            db.query(key1=val1,key2=val2) # AND

          Arguments:
            db.query({'key':val})
            db.query({'key1':val1,'key2':val2}) # AND
            db.query({'key1':val1,},{'key2':val2}) # AND (as different args)

        Nested queries can be accomplished with arguments. The key can take
        the following forms:
            - String starting with "$" and follows SQLite's JSON path. Must properly quote
              if it has dots, etc. No additional quoting is performed

                Example: {"$.key":'val'}            # Single key
                         {"$.key.subkey":'val'}     # Nested keys
                         {"$.key.subkey[3]":'val'}  # Nested keys to nested list.

            - Tuple string-keys or integer items. The quoteing will be handled for you!

                Example: {('key',): 'val'}
                         {('key','subkey'): 'val'}
                         {('key','subkey',3): 'val'}

            - Advaced queries (explained below)

        Advanced queries allow for more comparisons. Note: You must be careful
        about parentheses for operations. Keys are assigned with attributes (dot)
        and/or items (brackets). Items can have multiple comma-separated ones and
        can include integers for searching within a list.

          Example: db.query(db.Q.key == val)
                   db.query(db.Q['key'] == val)

                   db.query(db.Q.key.subkey == val)
                   db.query(db.Q['key'].subkey == val)
                   db.query(db.Q.key.['subkey'] == val)
                   db.query(db.Q['key','subkey'] == val)

                   qb.query(db.Q.key.subkey[3] == val)

          Complex Example:
            db.query((db.Q['other key',9] >= 4) & (Q().key < 3)) # inequality

        Queries support most comparison operations (==, !=, >,>=,<, <=, etc) plus:
            LIKE statements:  db.Q.key % "pat%tern"
            GLOB statements:  db.Q.key * "glob*pattern"
            REGEX statements: db.Q.key @ "regular.*expressions"

        db.query() is also aliased to db() and db.search()

        Inputs:
        ------
        *query_args:
            Arguments that are either dictionaries of equality key:value, or
            advanced queries

        **query_kwargs
            Keywords that are equality as explaied above

        _load [True]
            Whether or not to load the dict from JSON. Usually what is desired
            but may be useful if converting from sqlite3 to jsonl. Note that if not
            loaded, the result will not have rowid

        Returns:
        -------
        QueryResult -- An iterator of DBDicts. DBDicts are dicts with the 'rowid' attribute
                                   also specified
        """
        _load = query_kwargs.pop("_load", True)
        _1 = query_kwargs.pop("_1", False)

        if not query_args and not query_kwargs:
            return self.items(_load=_load)

        qobj = JSONLiteDB._combine_queries(*query_args, **query_kwargs)
        qstr, qvals = JSONLiteDB._qobj2query(qobj)

        res = self.db.execute(
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
        Return a single item from a query. See "query" for more details.

        Returns None if nothing matches

        db.query_one() is also aliased to db.one() and db.search_one()
        """
        query_kwargs["_1"] = True
        try:
            return next(self.query(*query_args, **query_kwargs))
        except StopIteration:
            return None

    search_one = one = query_one

    def count(self, *query_args, **query_kwargs):
        """
        Return the number of items that match the query
        rather than the items. See query() for details
        """
        qobj = JSONLiteDB._combine_queries(*query_args, **query_kwargs)
        qstr, qvals = JSONLiteDB._qobj2query(qobj)

        res = self.db.execute(
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
        JSON path, tuple, query object).

        Note that this is similar to

            >>> db.query(db.Q.path != None)

        but if you have items that are set as `None`, that query will miss it.

        Returns:
        -------
        QueryResult -- An iterator of DBDicts. DBDicts are dicts with the 'rowid' attribute
                                   also specified
        """
        path = split_query(path)
        if len(path) == 1:
            parent = Query()
            child = path[0]
        else:
            parent = path[:-1]
            child = path[-1]

        parent = build_index_paths(parent)[0]

        res = self.db.execute(
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
        Compute the aggregate of a given path/key.

        Valid functions are:
            avg, count, max, min, sum, total

        See https://www.sqlite.org/lang_aggfunc.html for description
        """
        allowed = {"AVG", "COUNT", "MAX", "MIN", "SUM", "TOTAL"}
        function = function.upper()
        if function not in allowed:
            raise ValueError(f"Unallowed aggregate function {function!r}")

        path = build_index_paths(path)[0]  # Always just one
        res = self.db.execute(
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
        qobj = JSONLiteDB._combine_queries(*query_args, **query_kwargs)
        qstr, qvals = JSONLiteDB._qobj2query(qobj)

        res = self.db.execute(
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
        Remove all items matching the input. See query() for how to
        query
        """
        qobj = JSONLiteDB._combine_queries(*query_args, **query_kwargs)
        qstr, qvals = JSONLiteDB._qobj2query(qobj)

        with self:
            self.db.execute(
                f"""
                DELETE FROM {self.table} 
                WHERE
                    {qstr}
                """,
                qvals,
            )

    def remove_by_rowid(self, *rowids):
        """
        Remove row by rowid. Can specify multiple for improved performance
        """
        with self:
            self.db.executemany(
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
        Get row by rowid. Can only specify one
        """
        row = self.db.execute(
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
        Return an iterator over all items. Order is likely insertion order but should not
        be relied upon
        """
        res = self.db.execute(f"SELECT rowid, data FROM {self.table}")

        return QueryResult(res, _load=_load)

    __iter__ = items

    def update(self, item, rowid=None, duplicates=False, _dump=True):
        """
        Update an entry with 'item'.

        Inputs:
        -------
        item
            Item to update. If 'item' has the attribute 'rowid',
            it will be inferred.

        rowid [None]
            Rowid of item. If not specified, will try to infer it from
            item's rowid attribute. Will raise a MissingRowIDError if it
            cannot infer it

        duplicates [False] -- Options: False, True, "ignore", "replace"
            How to handle duplicate items IF AND ONLY IF there is a "unique" index.
            If there isn't a unique index, items will be added regardless!
                False     : Do nothing but a unique index will cause an error
                True      : Same as "replace"
                "replace" : Replace items that violate a unique index
                "ignore"  : ignore items that violate a unique index

        _dump [True]
            Converts items to JSON. Set to False if input is already JSON.
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
            self.db.execute(
                f"""
                UPDATE {rtxt} {self.table}
                SET
                    data = JSON(?)
                WHERE
                    rowid = ?
                """,
                (item, rowid),
            )

    def path_counts(self, start=None):
        """
        Return a dictionary of all paths and number of items, optionally below
        "start" (default None).

        Inputs:
        ------
        start
            Starting path for all keys. Default is None which means it gives all paths
            at the root.

            Can be string (with '$' for a full path or just a single key without),
            a tuple/list, or a Query() object
        """
        start = start or "$"
        start = build_index_paths(start)[0]  # Always just one
        res = self.db.execute(
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
        Create an index. Indices can *dramatically* accelerate queries so use them
        if often querying some result.

        Note that order *does* matter when using multiple keys/paths. The order will be
        in order of arguments then order of keywords.

        Inputs:
        -------
        *paths
            Strings (either a single key or a JSON path), tuple, or query object.
            Query objects must *not* have values assigned to them (e.g. 'db.Q.key' is
            acceptable but 'db.Q.key == val' will fail).

        unique [False]
            Add a "UNIQUE" constraint to the index.

        Examples:
        ---------
            db.create_index('key1')                   # Single Key
            db.create_index('key1','key2')            # Multiple keys

            db.create_index(('key1','subkey'))        # Path with subkeys
            db.create_index(db.Q.onekey.twokey[3])    # Path w/ list index
            db.create_index(('onekey','twokey',3))    # Equiv to above

            db.create_index(db.Q.key1,db.Q.key2.subkey, db.Q.key3[4])
                                                      # Multiple advanced queries
        Note:
        -----
        sqlite3 is EXTREMELY sensitive to the form of the query. For example:
        db.create_index('key') and db.create_index('$.key'), which are identical,
        will not use the same index. (This is because the former becomes '$."key"'
        which is not the same as '$.key').
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
            self.db.execute(
                f"""
                CREATE {"UNIQUE" if unique else ""} INDEX IF NOT EXISTS {index_name} 
                ON {self.table}(
                    {quoted_paths}
                )"""
            )

    def drop_index_by_name(self, name):
        """Delete an index by name. The names can be found with the db.indexes attribute"""
        with self:  # Aparently this also must be manually quoted
            self.db.execute(f"DROP INDEX IF EXISTS {sqlite_quote(name)}")

    def drop_index(self, *paths, unique=False):
        """
        Delete an by query. Must match exactly as used to build index including
        unique settings
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
        res = self.db.execute(
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

    def _init(self):
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
            logger.debug("DB does not exists")

        with db:
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
                ("version", __version__),
            )

    @staticmethod
    def _combine_queries(*args, **kwargs):
        """Combine the different query types (see query()) into a qobj"""
        eq_args = []
        qargs = []
        for arg in args:
            if isinstance(arg, Query):
                qargs.append(arg)
            else:
                eq_args.append(arg)

        equalities = query_args(*eq_args, **kwargs)
        qobj = None
        for key, val in equalities.items():
            if qobj:
                qobj &= Query._from_equality(key, val)
            else:
                qobj = Query._from_equality(key, val)

        # Add the query args
        for arg in qargs:
            if qobj:
                qobj &= arg
            else:
                qobj = arg

        return qobj

    @staticmethod
    def _qobj2query(qobj):
        """
        Convert a finished query object to a query string and a list of
        query values
        """
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
        res = self.db.execute(f"SELECT COUNT(rowid) FROM {self.table}").fetchone()
        return res[0]

    def close(self):
        logger.debug("close")
        self.db.close()

    __del__ = close

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
            self.db.__enter__()  # Call the sqlite connection's __enter__
        self.context_count += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context_count -= 1
        if self.context_count == 0:
            self.db.__exit__(
                exc_type, exc_val, exc_tb
            )  # Call the sqlite connection's __exit__


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

        r = query_args({tuple(self._key): val})  # Will just return one item
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
            qdict = query_args({tuple(self._key): None})
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


def query_args(*args, **kwargs):
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
        arg = query_args(arg)  # Now it is a len-1 dict. Just use the key
        path = list(arg)[0]
        paths.append(path)

    paths.extend(query_args(kwargs).keys())
    return paths


def split_query(path):
    """
    This is the reverse of query_args and _build_index_paths.
    Splits a full JSON path into parts
    """
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
    quoted = io.StringIO()
    tempdb = sqlite3.connect(":memory:")
    tempdb.set_trace_callback(quoted.write)
    tempdb.execute("SELECT\n?", [text])
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
