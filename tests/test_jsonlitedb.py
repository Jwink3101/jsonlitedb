#!/usr/bin/env python
# -*- coding: utf-8 -*-

import contextlib
import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest

import jsonlitedb
from jsonlitedb import (
    AssignedQueryError,
    DissallowedError,
    JSONLiteDB,
    MissingRowIDError,
    MissingValueError,
    Q,
    Query,
    Row,
    cli,
)
from jsonlitedb import jsonlitedb as core
from jsonlitedb import parse_cli_filter_value, sqlite_quote


def test_JSONLiteDB_general():
    """
    Main tests. Note that these try to set different tables to verify that everything
    works for them too
    """
    db = JSONLiteDB(":memory:", table="mytable")

    assert str(db) == "JSONLiteDB(':memory:', table='mytable')"

    items = [
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
    ]
    db.insertmany(items[:3])
    db.insert(items[3])
    db.insert(json.dumps(items[4], indent=2), _dump=False)

    assert len(db) == 5

    # Test different ways to call queries
    assert (
        [{"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"}]
        == list(db.query(db.Q.first == "Paul"))
        == list(db(db.Q.first == "Paul"))  # __call__
        == list(db.search(db.Q.first == "Paul"))  # search
        == list(db(db.Q().first == "Paul"))  # () not needed but make it work
        == list(db(db.Query.first == "Paul"))
        == list(db(Query().first == "Paul"))
        == list(db(Q().first == "Paul"))
    )

    # Sorting / order by
    assert db.query(_orderby="born").all() == [
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
    ]
    assert db.query(_orderby="-born").all() == [
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
    ]

    assert db.query(_orderby=[db.Q.first, "born"]).all() == [
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
    ]
    assert db.query(_orderby=[db.Q.first, "-born"]).all() == [
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
    ]
    assert db.query(_orderby=[-db.Q.first, "-born"]).all() == [
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
    ]

    assert db.query(_orderby=["born", "-last"]).all() == [
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
    ]

    # Add repeat items
    for item in items:
        item["new"] = True
        db.insert(item)

    assert len(db) == 10

    # Simple query
    assert sorted(db.query(first="John"), key=lambda item: len(item)) == [
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {
            "first": "John",
            "last": "Lennon",
            "born": 1940,
            "role": "guitar",
            "new": True,
        },
    ]

    assert len(db.query(first="John", _limit=1).all()) == 1, "Failed _limit"

    # Multiple conditions. Also test _load = False
    assert (
        [
            {
                "first": "John",
                "last": "Lennon",
                "born": 1940,
                "role": "guitar",
                "new": True,
            }
        ]
        == list(db.query(db.Q.new == True, first="John"))
        == [
            json.loads(r) for r in db.query(db.Q.new == True, first="John", _load=False)
        ]
    )

    # Aggregates
    assert db.MIN("born") == 1926
    assert db.MAX("born") == 1943
    with pytest.raises(ValueError):
        db.aggregate("born", function="bla")

    # Bad query
    with pytest.raises(MissingValueError):
        db.count(db.Q.new)

    ## Using indexes
    assert db.explain_query({"last": "Starr"})[0]["detail"] == "SCAN mytable"
    assert db.analyze({"last": "Starr"}) == db.explain_query({"last": "Starr"})

    # Create an index of '$.last' but demonstrate this doesn't work
    # as expected because 'last' becomes '$."last"', not '$.last'
    db.create_index("$.last")
    assert db.indexes == {"ix_mytable_606e2153": ["$.last"]}
    assert db.explain_query({"last": "Starr"})[0]["detail"] == "SCAN mytable"

    db.drop_index_by_name("ix_mytable_606e2153")
    assert not db.indexes

    db.create_index("last")
    assert db.indexes == {"ix_mytable_1bd45eb5": ['$."last"']}
    assert db.explain_query({"last": "Starr"})[0]["detail"].startswith(
        "SEARCH mytable USING INDEX"
    )
    db.drop_index("last")

    db.create_index("bla", unique=False)
    db.create_index("bla", unique=True)
    assert db.indexes == {
        "ix_mytable_bdde088f": ['$."bla"'],
        "ix_mytable_bdde088f_UNIQUE": ['$."bla"'],
    }

    db.drop_index("bla")
    assert db.indexes == {"ix_mytable_bdde088f_UNIQUE": ['$."bla"']}

    db.drop_index("bla", unique=True)
    assert not db.indexes

    # rowid
    assert db.query_one({"last": "Starr"}).rowid == 4  # We never modified the order
    assert db.find_one({"last": "Starr"}).rowid == 4
    assert (
        "Ringo"
        == db[4]["first"]
        == db.get_by_rowid(4)["first"]
        == json.loads(db.get_by_rowid(4, _load=False))["first"]
    )
    with pytest.raises(TypeError):
        db[4, 5]
    with pytest.raises(IndexError):
        db[9999]

    ## Remove
    db.remove(new=True)
    assert len(db) == 5
    assert db.count(db.Q.first == "George") == 2
    assert db.count((db.Q.first == "George") & (db.Q.last == "Martin")) == 1

    ## Unique, etc
    with pytest.raises(sqlite3.IntegrityError):
        db.create_index("first", unique=True)

    db.create_index("first", "last", unique=True)

    # demonstrate failure without replace
    for item in items:
        item["new"] = True
        with pytest.raises(sqlite3.IntegrityError):
            db.insert(item)

    # Now use duplicates=True and duplicates="replace". Should be same behavior
    n0 = len(db)  # 5
    for item in items:
        item["new"] = 1
        db.insert(item, duplicates=True)
    assert db.count(new=1) == 5
    assert len(db) == n0, "Replace failed"

    for item in items:
        item["new"] = 2
        db.insert(item, duplicates="replace")
    assert db.count(new=2) == 5
    assert len(db) == n0, "Replace failed"

    # Now use ignore
    for item in items:
        item["new"] = 2
        db.insert(item, duplicates="ignore")
    assert db.count(new=2) == 5, "Replaced instead of ignored"
    assert len(db) == n0, "Ignore failed"

    # Now remove it and do it again. Show that even with duplicates=True, it still
    # duplicated
    db.drop_index("first", "last", unique=True)
    for item in items:
        item["new"] = True
        db.insert(item, duplicates=True)
    assert len(db) == 2 * n0

    # Test the error
    with pytest.raises(ValueError):
        db.insert(item, duplicates="bla")

    # reset it
    for item in items:
        del item["new"]
        db.insert(item)
    db.remove((db.Q.new == True) | (db.Q.new == 2))
    assert len(db) == n0

    # Rowid tests
    db.insert(dict(new=True, item="random"))
    del db[db.query_one(new=True).rowid]
    assert db.count(new=True) == 0

    with pytest.raises(TypeError):
        del db[1, 2, 3]  # Can't do a tuple

    with pytest.raises(IndexError):
        del db[123456789]  # Must be an existing rowid

    ## Advanced Queries
    assert db.count(Q().born <= 1940) == 3
    assert db.count(Q().born >= 1942) == 2
    assert db.count((Q().born >= 1942) | (Q().role == "producer")) == 3
    assert db.count((Q().born >= 1942) | (Q().role % "prod%")) == 3
    assert db.count((db.Q.born >= 1942) & (Q().role % "prod%")) == 0  # Also test db.Q

    assert db.count(~(Q().born <= 1940)) == 2
    assert db.count(Q().born != 1926) == 4

    assert db.count(db.Q.role % "prod%") == 1
    assert db.count(db.Q.role * "prod*") == 1
    assert db.count(db.Q.role @ "prod") == 1
    assert db.count(db.Q.role @ "prod.c") == 1
    assert db.count(db.Q.role @ "prod.*r") == 1
    assert db.count(db.Q.role @ "prod.x") == 0
    assert db.count(_limit=2) == 2
    assert db.count(_limit=2, _orderby="-born") == 2

    # Limits
    assert len(db(db.Q.born > 0).all()) == 5
    assert len(db(db.Q.born > 0, _limit=3).all()) == 3
    assert len(db(db.Q.born > 0, _limit=10).all()) == 5

    ## Single returns
    assert (
        "George"
        == db.query_one(first="George")["first"]
        == db.search_one(first="George")["first"]  # alias
        == db.one(first="George")["first"]  # alias
    )
    assert db.query_one(first="George", last="Lennon") is None

    ## Iterate
    assert list(db) == list(db.query())
    assert len(list(db)) == 5

    # Directly execute
    assert (
        db.execute(
            """
            SELECT
                data ->> '$.first' as FiRsT
            FROM mytable
            WHERE
                JSON_EXTRACT(data,'$.last') == 'Lennon'
            """
        ).fetchone()["FiRsT"]
        == "John"
    )

    # Purge
    assert len(db) > 0  # baseline
    db.purge()
    assert len(db) == 0

    with pytest.raises(ValueError):
        db.wal_checkpoint(mode="NOT VALID")
    db.wal_checkpoint(mode="TRUNCATE")


def test_JSONLiteDB_file():
    ##########################################################
    ## Test with a real db
    ##########################################################
    name = Path("!!!TEST_TMP.db")
    try:
        db = JSONLiteDB(name, table="bla")
        db.insert({"key1": "val1"})
        db.insert({"key2": "val2"})
        db.create_index("key1")
        del db

        # Make a fake index to test the extract part
        db = sqlite3.connect(name)
        with db:
            db.execute("CREATE INDEX tmp ON bla (rowid)")
        db.close()

        db = JSONLiteDB(name, table="bla")
        assert len(db) == 2
        # Make sure we don't see 'tmp' index. Just the one we made
        assert db.indexes == {"ix_bla_8c01cd08": ['$."key1"']}

        print(db.about())

        # Directly read-only
        db = JSONLiteDB(f"file:{name}?mode=ro", table="bla", uri=True)
        assert str(db) == (
            "JSONLiteDB('file:!!!TEST_TMP.db?mode=ro', table='bla', **{'uri': True})"
        )
        assert len(db) == 2
        with pytest.raises(sqlite3.OperationalError):
            db.drop_index("key1")

        # with the read_only() method
        db = JSONLiteDB.read_only(name, table="bla")
        assert str(db) == (
            "JSONLiteDB('file:!!!TEST_TMP.db?mode=ro', table='bla', **{'uri': True})"
        )
        assert len(db) == 2
        with pytest.raises(sqlite3.OperationalError):
            db.drop_index("key1")

    finally:
        name.unlink()


def test_JSONLiteDB_dbconnection():
    db0 = sqlite3.connect(":memory:")
    db1 = JSONLiteDB(db0)

    assert db1.db is db0

    repr(db1)
    db1.insert(dict(key="value", other=dict(key="other value")))

    row = db0.execute(
        """
    SELECT data
    FROM items"""
    ).fetchall()
    assert len(row) == 1
    assert json.loads(row[0]["data"]) == {
        "key": "value",
        "other": {"key": "other value"},
    }

    # Test backup. Use the db1.db as db1 is JSONLiteDB
    db2 = sqlite3.connect(":memory:")
    db1.db.backup(db2)
    db3 = JSONLiteDB(db2)
    assert db3.db is db2
    assert db2 is not db0
    assert db3.count(db3.Q.other.key == "other value") == 1

    db4 = JSONLiteDB(db1.db)
    assert db4.db is db1.db and db1.db is db0
    assert len(db1) == 1
    db4.insert({"this": "is", "a": ["new", "object"]})
    assert len(db1) == len(db4) == 2


def test_JSONLiteDB_adv():
    ##########################################################
    ## Subqueries & other Advanced.
    ## Based on Advanced Usage doc but does not need to be exact
    ##########################################################
    # .connect is identical. Just there to match the sqlite3 call
    db = JSONLiteDB.connect(":memory:", table="contacts")
    db.insert(
        {
            "first": "John",
            "last": "Smith",
            "phone": {"home": "215.555.6587", "work": "919.555.4795"},
            "kids": [
                {"first": "John Jr.", "last": "Smith"},
                {"first": "Jane", "last": "Smith"},
            ],
        }
    )
    db.insert(
        {
            "first": "Clark",
            "last": "Drake",
            "phone": {"home": "412.555.4960", "work": "410.555.9903"},
            "kids": [],
            "extra": "This is extra",
            "extra1": {"extra2": "even more extra"},
            "extra2": None,
        }
    )
    db.insert(
        {
            "first": "Peggy",
            "last": "Line",
            "phone": {"home": "505.555.3101"},
            "kids": [
                {"first": "Jane", "last": "Line"},
                {"first": "Molly", "last": "Line"},
            ],
        }
    )
    db.insert(
        {
            "first": "Luke",
            "last": "Truss",
            "phone": {"home": "610.555.2647"},
            "kids": [{"first": "Janet", "last": "Truss"}],
        }
    )

    assert (
        [
            {
                "first": "Peggy",
                "last": "Line",
                "phone": {"home": "505.555.3101"},
                "kids": [
                    {"first": "Jane", "last": "Line"},
                    {"first": "Molly", "last": "Line"},
                ],
            }
        ]
        == list(db.query({("phone", "home"): "505.555.3101"}))
        == list(db.query({'$."phone"."home"': "505.555.3101"}))
        == list(db.query(db.Q.phone.home == "505.555.3101"))
        == list(db.query({"$.phone.home": "505.555.3101"}))
        == list(db.query(db.Q.phone.home % "505%"))
        == list(db.query(db.Q.phone.home * "505*"))
        == list(db.query(db.Q.phone.home @ "505.*"))
    )

    # Key Counts
    assert db.path_counts() == {
        "first": 4,
        "kids": 4,
        "last": 4,
        "phone": 4,
        "extra": 1,
        "extra1": 1,
        "extra2": 1,
    }
    assert db.path_counts("extra") == {}  # no subitems. Just strings
    assert set(db.keys()) == {
        "extra",
        "extra1",
        "extra2",
        "first",
        "kids",
        "last",
        "phone",
    }

    assert (
        {"extra2": 1}
        == db.path_counts("extra1")
        == db.path_counts(("extra1",))
        == db.path_counts(db.Q.extra1)
    )

    assert db.path_counts(db.Q.extra1.extra2) == {}  # Again, no sub-items
    assert db.path_counts(db.Q.bla) == {}

    # Test query by null
    assert [item["first"] for item in db.query(db.Q.extra != None)] == ["Clark"]
    assert db.count(db.Q.extra1 != None) == 1  # has extra1
    assert db.count(db.Q.extra1 == None) == 3  # does not have extra1

    # Test known issue. Cannot distinguish between None and missing.
    # But then use
    assert db.count(db.Q.extra2 != None) == 0
    assert db.count(db.Q.extra2 == None) == 4

    assert db.count(db.Q.made.up.key != None) == 0
    assert db.count(db.Q.made.up.key == None) == 4

    # This will now work to detect extra2
    assert list(db.query_by_path_exists(db.Q.extra2)) == [
        {
            "extra": "This is extra",
            "extra1": {"extra2": "even more extra"},
            "extra2": None,
            "first": "Clark",
            "kids": [],
            "last": "Drake",
            "phone": {"home": "412.555.4960", "work": "410.555.9903"},
        }
    ]

    assert [
        json.loads(r) for r in db.query_by_path_exists(db.Q.extra2, _load=False)
    ] == list(db.query_by_path_exists(db.Q.extra2))
    assert db.count_by_path_exists(db.Q.extra2) == 1

    assert list(db.query_by_path_exists(db.Q.made.up.key)) == []
    assert db.count_by_path_exists(db.Q.made.up.key) == 0

    # Nested. Look at second kid
    assert list(db.query_by_path_exists(db.Q.kids[1])) == [
        {
            "first": "John",
            "kids": [
                {"first": "John Jr.", "last": "Smith"},
                {"first": "Jane", "last": "Smith"},
            ],
            "last": "Smith",
            "phone": {"home": "215.555.6587", "work": "919.555.4795"},
        },
        {
            "first": "Peggy",
            "kids": [
                {"first": "Jane", "last": "Line"},
                {"first": "Molly", "last": "Line"},
            ],
            "last": "Line",
            "phone": {"home": "505.555.3101"},
        },
    ]

    # No path means empty
    assert list(db.query_by_path_exists(None)) == []
    assert db.count_by_path_exists(None) == 0


def test_JSONLiteDB_unicode():
    db = JSONLiteDB.memory(table="uni")
    db.insert({"kéy": "vælů€", "k2": "val"})
    db.insert({"kéy": "vælůe", "k2": "vàl"})
    db.insert({"kéy": "vælu€", "k2": "vál"})

    # Maintain's unicode
    assert list(db) == [
        {"kéy": "vælů€", "k2": "val"},
        {"kéy": "vælůe", "k2": "vàl"},
        {"kéy": "vælu€", "k2": "vál"},
    ]

    assert db.count(k2="vàl") == 1
    assert (
        1
        == db.count(kéy="vælu€")
        == db.count(db.Q.kéy == "vælu€")
        == db.count(db.Q["kéy"] == "vælu€")
    )


def test_JSONLiteDB_updates():
    ##########################################################
    ## Updates
    ##########################################################
    items = [
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
    ]
    db = JSONLiteDB(":memory:")
    db.insert(*items)

    row = db.query_one(first="Paul")
    row["knighted"] = 1997
    db.update(row)

    assert db.query_one(first="Paul")["knighted"] == 1997

    # show that the infered is not used if specified
    row["new"] = True
    db.update(row, rowid=9999)
    assert db.count(new=True) == 0

    # Demonstrate that insert still works even though it has a rowid
    db.insert(row)
    assert row.rowid == 2, "rowid should exist and be unchanged on inserted item"
    assert db.count(new=True) == 1
    assert db.query_one(new=True).rowid == 6
    db.remove(new=True)

    row = db.query_one(first="Ringo")
    rowid = row.rowid
    row = dict(row)
    assert not hasattr(row, "rowid")
    row["knighted"] = 2018

    with pytest.raises(MissingRowIDError):
        db.update(row)
    db.update(row, rowid=rowid)
    assert db.query_one(first="Ringo")["knighted"] == 2018

    # Test with unique index
    # forgive the obvious historical inaccuracy
    db.create_index("knighted", unique=True)

    row = db.query_one(last="Martin")
    row["knighted"] = 2018

    with pytest.raises(sqlite3.IntegrityError):
        db.update(row)

    db.update(row, duplicates="ignore")
    assert "knighted" not in db.query_one(last="Martin")
    assert db.query_one(first="Ringo").get("knighted", None) == 2018

    with pytest.raises(ValueError):
        db.update(row, duplicates="bla")

    db.update(row, duplicates="replace")
    assert db.query_one(last="Martin").get("knighted", None) == 2018, "not replaced!"
    assert db.count(first="Ringo") == 0, "conflict should have been deleted"


def test_JSONLiteDB_update_many():
    items = [
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
    ]
    db = JSONLiteDB(":memory:")
    db.insertmany(items)

    db.update()

    rows = db.query(db.Q.role == "guitar").all()
    for row in rows:
        row["role"] = "strings"
    db.update_many(rows)

    assert db.count(role="guitar") == 0
    assert db.count(role="strings") == 2

    row = db.query_one(first="Paul")
    db.update_many([(dict(row, role="keys"), row.rowid)])
    assert db.query_one(first="Paul")["role"] == "keys"

    with pytest.raises(MissingRowIDError):
        db.update(dict(row, role="keys"), dict(row, role="keys"), rowid=row.rowid)

    with pytest.raises(MissingRowIDError):
        db.update((dict(row, role="keys"), row.rowid), rowid=row.rowid)

    with pytest.raises(MissingRowIDError):
        db.update_many([{"first": "Nope"}])


def test_JSONLiteDB_query_results():
    db = JSONLiteDB(":memory:")
    items = [{"i": i} for i in range(10)]
    db.insertmany(items)

    res = db.query()
    assert isinstance(res, jsonlitedb.QueryResult)

    assert next(res) == {"i": 0}
    assert res.fetchone() == {"i": 1}
    assert res.fetchmany(3) == [{"i": 2}, {"i": 3}, {"i": 4}]
    for c, item in enumerate(res):
        assert item == {"i": c + 5}  # +5 because we already some above

    # fetchone() returns None at end while others raise StopIteration
    with pytest.raises(StopIteration):
        next(res)
    with pytest.raises(StopIteration):
        res.next()
    assert res.fetchone() is None

    assert res.fetchmany() == []

    assert list(db.query()) == db.query().fetchall() == list(db) == items
    assert db.query().all() == items

    assert (
        {"i": 3}
        == db(db.Q.i == 3).one()
        == next(db({"i": 3}))
        == json.loads(db(db.Q.i == 3, _load=False).one())
    )


def test_JSONLiteDB_patch():
    """
    Main tests. Note that these try to set different tables to verify that everything
    works for them too
    """
    db = JSONLiteDB(":memory:", table="mytable")

    assert str(db) == "JSONLiteDB(':memory:', table='mytable')"

    items = [
        {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"},
        {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"},
        {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"},
        {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"},
        {"first": "George", "last": "Martin", "born": 1926, "role": "producer"},
    ]
    db.insertmany(items)

    db.patch(
        {
            "first": "Richard",
            "last": "Starkey",
            "status": "active",  # This is a new field
            "role": None,  # This will be removed.
        },
        (db.Q.last == "Starr"),
    )

    assert db.path_counts().get("status", -1) == 1  # Was added
    assert db.path_counts().get("role", -1) == 4  # Was removed
    assert db.count(first="Ringo") == 0
    assert db.count(first="Richard") == 1


def test_JSONLiteDB_stats():
    db = JSONLiteDB(":memory:")
    db.insert({"a": 1}, {"a": 2})
    db.create_index("a")

    stats = db.stats()
    assert stats["dbpath"] == ":memory:"
    assert stats["table"] == "items"
    assert stats["rows"] == 2
    assert stats["indexes"] == db.indexes
    assert stats["page_size"] > 0
    assert stats["page_count"] >= 1
    assert stats["bytes"] == stats["page_size"] * stats["page_count"]


def test_JSONLiteDB_import_export_jsonl(tmp_path):
    items = [{"a": 1}, {"a": 2}, {"a": 3}]
    db = JSONLiteDB(":memory:")
    db.insertmany(items)

    jsonl_path = tmp_path / "data.jsonl"
    db.export_jsonl(jsonl_path)

    db2 = JSONLiteDB(":memory:")
    db2.import_jsonl(jsonl_path)
    assert list(db2) == items

    json_path = tmp_path / "data.json"
    json_path.write_text(json.dumps(items))
    db3 = JSONLiteDB(":memory:")
    db3.import_jsonl(json_path)
    assert list(db3) == items

    json_single_path = tmp_path / "single.json"
    json_single_path.write_text(json.dumps({"a": 10}))
    db4 = JSONLiteDB(":memory:")
    db4.import_jsonl(json_single_path)
    assert list(db4) == [{"a": 10}]


def test_Query():
    import pytest

    # Building the keys
    assert Query().key._key == ["key"]
    assert Query().key.subkey._key == ["key", "subkey"]
    assert Query()[1]._key == [1]
    assert Query().key[1]._key == ["key", 1]
    assert Query().key[1, 1]._key == ["key", 1, 1]
    assert Query().key[1][1]._key == ["key", 1, 1]
    assert Query().key["subkey"]._key == ["key", "subkey"]
    assert (
        Query().key["subkey", "subsubkey"]._key
        == Query().key["subkey"].subsubkey._key
        == ["key", "subkey", "subsubkey"]
    )
    assert (Query() + "a")._key == ["a"]
    assert (Query() + "a" + 1 + 3)._key == ["a", 1, 3]

    # Errors
    with pytest.raises(DissallowedError):
        Query().q = 100

    with pytest.raises(DissallowedError):
        Query()[1] = 100

    # For these tests, core.translate the fill but this WILL NOT BE THE REAL QUERY. It will
    # later be replaced with question marks
    q = Query().a == 10
    assert (
        core.translate(q._query, q._qdict) == "( JSON_EXTRACT(data, '$.\"a\"') = 10 )"
    )

    q = Query().a < 10
    assert (
        core.translate(q._query, q._qdict) == "( JSON_EXTRACT(data, '$.\"a\"') < 10 )"
    )

    q1 = Query().a["b"] < 10
    q2 = Query()["a", "b"] < 10
    q3 = Query()["a"].b < 10
    assert (
        core.translate(q1._query, q1._qdict)
        == core.translate(q2._query, q2._qdict)
        == core.translate(q3._query, q3._qdict)
        == '( JSON_EXTRACT(data, \'$."a"."b"\') < 10 )'
    )

    q = (Query().a < "A") | (Query().b < "B")
    assert (
        core.translate(q._query, q._qdict)
        == "( ( JSON_EXTRACT(data, '$.\"a\"') < A ) OR ( JSON_EXTRACT(data, '$.\"b\"') < B ) )"
    )

    q = (Query().a < "A") | (Query().b == "B") & (
        (Query().c != "C") | ~(Query().d >= "D")
    )
    assert core.translate(q._query, q._qdict) == (
        "( ( JSON_EXTRACT(data, '$.\"a\"') < A ) "
        "OR ( ( JSON_EXTRACT(data, '$.\"b\"') = B ) "
        "AND ( ( JSON_EXTRACT(data, '$.\"c\"') != C ) "
        "OR ( NOT ( JSON_EXTRACT(data, '$.\"d\"') >= D ) ) ) ) )"
    )

    assert repr(Query().key) == "Query(JSON_EXTRACT(data, '$.\"key\"'))"
    assert repr(Query().key.subkey) == 'Query(JSON_EXTRACT(data, \'$."key"."subkey"\'))'
    assert repr(Query()) == "Query()"

    q = Query().a > "A"
    q |= Query().b < "B"
    assert (
        core.translate(q._query, q._qdict)
        == "( ( JSON_EXTRACT(data, '$.\"a\"') > A ) OR ( JSON_EXTRACT(data, '$.\"b\"') < B ) )"
    )

    equalities = {'$."val1"': "val1", '$."val2"': "val2"}
    q = None
    for key, val in equalities.items():
        if q:
            q &= Query._from_equality(key, val)
        else:
            q = Query._from_equality(key, val)
    assert (
        core.translate(q._query, q._qdict)
        == "( ( JSON_EXTRACT(data, '$.\"val1\"') = val1 ) AND ( JSON_EXTRACT(data, '$.\"val2\"') = val2 ) )"
    )

    # Tricks for LIKE, GLOB, and REGEXP
    assert (
        repr(Q().a % "TE%ST") == "Query(( JSON_EXTRACT(data, '$.\"a\"') LIKE 'TE%ST' ))"
    )
    assert (
        repr(Q().a * "TE*ST") == "Query(( JSON_EXTRACT(data, '$.\"a\"') GLOB 'TE*ST' ))"
    )
    assert (
        repr(Q().a @ "TE.ST")
        == "Query(( JSON_EXTRACT(data, '$.\"a\"') REGEXP 'TE.ST' ))"
    )

    # DO NOT allow paired comparisons
    with pytest.raises(ValueError):
        4 <= Query().val <= 5

    # Logic w/o values
    with pytest.raises(MissingValueError):
        Query().key | Query().key
    with pytest.raises(MissingValueError):
        (Query().key == 1) | Query().key
    with pytest.raises(MissingValueError):
        Query().key | (Query().key == 2)

    (Query().key == 1) | (Query().key == 2)  # No error

    with pytest.raises(MissingValueError):
        Query() | Query()


def test_query_args():
    import pytest

    with pytest.raises(ValueError):
        core._query_tuple2jsonpath({frozenset(("key", "subkey", 3)): "val"})

    assert (
        core._query_tuple2jsonpath(key="val")
        == core._query_tuple2jsonpath({"key": "val"})
        == {'$."key"': "val"}
    )
    assert (
        core._query_tuple2jsonpath({1: "val"})
        == core._query_tuple2jsonpath({(1,): "val"})
        == {"$[1]": "val"}
    )  # Include first of a tuple
    assert core._query_tuple2jsonpath({("key", "subkey"): "val"}) == {
        '$."key"."subkey"': "val"
    }  # Notice it's quoted
    assert core._query_tuple2jsonpath(
        {
            ("key",): "val",
            ("key", 1): "val",
            ("key", 1, 2): "val",
            ("key", 1, 2, "subkey"): "val",
            ("key", 1, 2, "subkey", 3): "val",
            ("key", "subkey", 30): "val",
            ("key", "subkey", 1, 3): "val",
        },
        dkey="val",
    ) == {
        '$."key"': "val",
        '$."key"[1]': "val",
        '$."key"[1][2]': "val",
        '$."key"[1][2]."subkey"': "val",
        '$."key"[1][2]."subkey"[3]': "val",
        '$."key"."subkey"[30]': "val",
        '$."key"."subkey"[1][3]': "val",
        '$."dkey"': "val",
    }

    # non-dicts
    assert core._query_tuple2jsonpath("key", '$."key"', ("key", "subkey")) == {
        '$."key"': None,
        '$."key"."subkey"': None,
    }


def test_build_index_paths():
    import pytest

    assert core.build_index_paths("key") == ['$."key"']
    assert core.build_index_paths("key1", "key2") == [
        '$."key1"',
        '$."key2"',
    ]
    assert core.build_index_paths("key", ("key", "subkey"), "$.key2.sub2") == [
        '$."key"',
        '$."key"."subkey"',
        "$.key2.sub2",
    ]
    assert core.build_index_paths(
        Query().key, Query().key.subkey, Query()[2], Query().key[3], Query().key.sub[1]
    ) == ['$."key"', '$."key"."subkey"', "$[2]", '$."key"[3]', '$."key"."sub"[1]']

    with pytest.raises(AssignedQueryError):
        core.build_index_paths(Query().key == "val")

    with pytest.raises(AssignedQueryError):
        core.build_index_paths({"key": "val"})


def test_query2sql():
    qstr, qvals = JSONLiteDB._query2sql(key="val")
    keys = re.findall(r":jldb_[0-9a-f]+", qstr)
    assert len(keys) == 1
    assert qstr == f"( JSON_EXTRACT(data, '$.\"key\"') = {keys[0]} )"
    assert qvals == {keys[0].removeprefix(":"): "val"}

    qstr, qvals = JSONLiteDB._query2sql(
        (Query().val3 == "val3"),
        ((Query().val4 == "val4") | (Query().val4 == "otherval4")),
        val1="val1",
        val2="val2",
    )

    assert re.sub(r":jldb_[0-9a-f]+", "?", qstr) == (
        """( ( ( ( """
        """JSON_EXTRACT(data, '$."val1"') = ? ) """
        """AND ( JSON_EXTRACT(data, '$."val2"') = ? ) ) """
        """AND ( JSON_EXTRACT(data, '$."val3"') = ? ) ) """
        """AND ( ( JSON_EXTRACT(data, '$."val4"') = ? ) """
        """OR ( JSON_EXTRACT(data, '$."val4"') = ? """
        """) ) )"""
    )
    keys = re.findall(r":jldb_[0-9a-f]+", qstr)
    assert [qvals[k.removeprefix(":")] for k in keys] == [
        "val1",
        "val2",
        "val3",
        "val4",
        "otherval4",
    ]


def test_query_placeholder_token_in_path():
    db = JSONLiteDB(":memory:")
    item = {"!>>boom<<!": 1, "safe": "ok"}
    db.insert(item)

    # Regression: placeholder-like text in JSON path must not be parsed as a bind token.
    rows = list(db.query({'$."!>>boom<<!"': 1}))
    assert rows == [item]


def test_disable_regex():
    old_disable = core.DISABLE_REGEX
    core.DISABLE_REGEX = True
    try:
        db = JSONLiteDB(":memory:")
        db.insert({"a": "TE.ST"})
        with pytest.raises(sqlite3.OperationalError, match="no such function: REGEXP"):
            db.query(db.Q.a @ "TE.ST").all()
    finally:
        core.DISABLE_REGEX = old_disable


def test_init_handles_missing_metadata_table():
    def fake_about(_self):
        raise sqlite3.OperationalError("no such table: items_kv")

    old_about = JSONLiteDB.about
    JSONLiteDB.about = fake_about
    try:
        db = JSONLiteDB(":memory:")
        assert db.count() == 0
    finally:
        JSONLiteDB.about = old_about


def test_init_reraises_unexpected_operational_error():
    def fake_about(_self):
        raise sqlite3.OperationalError("database is locked")

    old_about = JSONLiteDB.about
    JSONLiteDB.about = fake_about
    try:
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            JSONLiteDB(":memory:")
    finally:
        JSONLiteDB.about = old_about


def test_disable_metadata_env_var(tmp_path, monkeypatch):
    dbpath = tmp_path / "nometa.db"
    old_disable_metadata = core.DISABLE_METADATA
    monkeypatch.setattr(core, "DISABLE_METADATA", True)

    try:
        db = JSONLiteDB(dbpath)
        db.insert({"x": 1})

        rows = db.execute(f"SELECT key,val FROM {db.table}_kv ORDER BY key").fetchall()
        assert rows == []
        assert db.about() == ("**MISSING**", "**MISSING**")

        # Re-open and verify missing metadata rows do not break initialization.
        db = JSONLiteDB(dbpath)
        assert db.count() == 1
        assert db.about() == ("**MISSING**", "**MISSING**")
    finally:
        core.DISABLE_METADATA = old_disable_metadata


def test_build_orderby_pairs():
    db = JSONLiteDB.memory()

    tests = [
        # Type 1
        ("$.key", [("$.key", "ASC")]),
        ("+$.key", [("$.key", "ASC")]),
        ("-$.key", [("$.key", "DESC")]),
        ("$.key.subkey", [("$.key.subkey", "ASC")]),
        ("+$.key.subkey", [("$.key.subkey", "ASC")]),
        ("-$.key.subkey", [("$.key.subkey", "DESC")]),
        ("$.key.subkey[3]", [("$.key.subkey[3]", "ASC")]),
        ("+$.key.subkey[3]", [("$.key.subkey[3]", "ASC")]),
        ("-$.key.subkey[3]", [("$.key.subkey[3]", "DESC")]),
        # Type 2
        ("key", [('$."key"', "ASC")]),
        ("+key", [('$."key"', "ASC")]),
        ("-key", [('$."key"', "DESC")]),
        # Type 3
        (("key",), [('$."key"', "ASC")]),
        (("+key",), [('$."key"', "ASC")]),
        (("-key",), [('$."key"', "DESC")]),
        (("key", "subkey"), [('$."key"."subkey"', "ASC")]),
        (("+key", "subkey"), [('$."key"."subkey"', "ASC")]),
        (("-key", "subkey"), [('$."key"."subkey"', "DESC")]),
        (("key", "subkey", 3), [('$."key"."subkey"[3]', "ASC")]),
        (("+key", "subkey", 3), [('$."key"."subkey"[3]', "ASC")]),
        (("-key", "subkey", 3), [('$."key"."subkey"[3]', "DESC")]),
        # Type 4
        (db.Q.key, [('$."key"', "ASC")]),
        (+db.Q.key, [('$."key"', "ASC")]),
        (-db.Q.key, [('$."key"', "DESC")]),
        (db.Q.key.subkey, [('$."key"."subkey"', "ASC")]),
        (+db.Q.key.subkey, [('$."key"."subkey"', "ASC")]),
        (-db.Q.key.subkey, [('$."key"."subkey"', "DESC")]),
        (db.Q.key.subkey[3], [('$."key"."subkey"[3]', "ASC")]),
        (+db.Q.key.subkey[3], [('$."key"."subkey"[3]', "ASC")]),
        (-db.Q.key.subkey[3], [('$."key"."subkey"[3]', "DESC")]),
        # Special cases
        ((4,), [("$[4]", "ASC")]),
        ((-4,), [("$[-4]", "ASC")]),  # Note that this does not reverse direction
        (db.Q[4], [("$[4]", "ASC")]),
        (db.Q[-4], [("$[-4]", "ASC")]),
        (-db.Q[4], [("$[4]", "DESC")]),  # This DOES reverse
        (-db.Q[-4], [("$[-4]", "DESC")]),  # this DOES reverse
    ]

    for input_value, expected in tests:
        assert core.build_orderby_pairs(input_value) == expected

    # Catch edge cases
    assert core.build_orderby_pairs(None) == ""

    with pytest.raises(ValueError):
        core.build_orderby_pairs(db.Q.key == "val")
    with pytest.raises(ValueError):
        core.build_orderby_pairs([tuple()])
    with pytest.raises(ValueError):
        core.build_orderby_pairs(object())


def test_split_query():
    assert (
        ("a",)
        == core.split_query("a")
        == core.split_query(Q().a)
        == core.split_query(("a",))
    )
    assert (
        ("a", "b")
        == core.split_query("$.a.b")
        == core.split_query('$."a"."b"')
        == core.split_query(("a", "b"))
        == core.split_query(Q().a.b)
        == core.split_query(Q().a["b"])
    )
    assert (
        ("a", 1)
        == core.split_query("$.a[1]")
        == core.split_query('$."a"[1]')
        == core.split_query(("a", 1))
        == core.split_query(Q().a[1])
    )
    assert (
        ("a", 1)
        == core.split_query("$.a[1]")
        == core.split_query('$."a"[1]')
        == core.split_query(("a", 1))
        == core.split_query(Q().a[1])
    )

    assert ("a", "b", 1) == core.split_query(Q().a.b[1])

    assert core.split_query(Q()[1]) == (1,)
    assert core.split_query(Q()[1].a) == (1, "a")
    assert core.split_query(Q().a[1][2]) == ("a", 1, 2)
    assert core.split_query(Q().a[1].b[2]) == ("a", 1, "b", 2)
    g = ("a", 1, "b", 2, "c", 3, 4, 5, "six", 7, "eight", 9)
    assert core.split_query(Q().a[1].b[2].c[3, 4][5]["six", 7].eight[9]) == g


def test_Row():
    # There is a slight incompatibility of CPython and PyPy's sqlite3.Row that the
    # version here breaks. The PyPy version defines a "values" attribute (a tuple)
    # while the CPython one doesn't have the attribute. Therefore, when JSONLiteDB.Row
    # defines the method (returning an iterator), it gets messed up.
    #
    # The method is there for completeness but isn't actually used outside of this unit
    # test. Therefore, we skip it for PyPy. Other tests continue to pass so the code
    # is still safe.
    import platform

    if platform.python_implementation() == "PyPy":  # pragma: no cover
        print("SKIPPING test in PyPy")
        return

    db = sqlite3.connect(":memory:")
    db.row_factory = Row
    row = db.execute("""SELECT 'a val' as a, 'b val' as b""").fetchone()

    assert row.keys() == ["a", "b"]  # not set() to check orderings
    assert row.todict() == {"a": "a val", "b": "b val"}
    assert set(row.items()) == {("a", "a val"), ("b", "b val")}
    assert set(row.values()) == {"a val", "b val"}
    assert row.get("a") == "a val"
    assert row.get("c", "c val") == "c val"
    assert str(row) == "Row({'a': 'a val', 'b': 'b val'})"


def test_listify():
    assert core.listify(None) == []
    assert core.listify(["a"]) == core.listify("a") == ["a"]
    l = ["a", "b", "c"]
    assert core.listify(l) == l
    assert core.listify(l) is l

    assert core.listify((1, 2)) == [1, 2]
    assert core.listify((1, 2), expand_tuples=True) == [1, 2]
    assert core.listify((1, 2), expand_tuples=False) == [(1, 2)]


def test_group_ints_with_preceding_string():
    assert core.group_ints_with_preceding_string([1, 2]) == [[1, 2]]
    assert core.group_ints_with_preceding_string(["a", "b"]) == [["a"], ["b"]]
    assert core.group_ints_with_preceding_string(["a", 1, 2, 3, "b"]) == [
        ["a", 1, 2, 3],
        ["b"],
    ]
    assert core.group_ints_with_preceding_string([1, 2, 3, "b"]) == [
        [1, 2, 3],
        ["b"],
    ]
    assert core.group_ints_with_preceding_string(["a", "b", 1, 2, "3", 4]) == [
        ["a"],
        ["b", 1, 2],
        ["3", 4],
    ]
    # Example ones
    assert core.group_ints_with_preceding_string
    assert core.group_ints_with_preceding_string(["A", "B", "C"]) == [
        ["A"],
        ["B"],
        ["C"],
    ]  # Nothing
    assert core.group_ints_with_preceding_string(["A", 1, "B", 2, 3, "C"]) == [
        ["A", 1],
        ["B", 2, 3],
        ["C"],
    ]
    assert core.group_ints_with_preceding_string([1, 2, "A", "B", 3]) == [
        [1, 2],
        ["A"],
        ["B", 3],
    ]


def test_sqlite_quote():
    assert sqlite_quote("hi") == "'hi'"
    assert sqlite_quote("h'i") == "'h''i'"
    assert sqlite_quote("hi -- comment") == "'hi -- comment'"
    assert (
        sqlite_quote("Robert'); DROP TABLE Students;--")
        == "'Robert''); DROP TABLE Students;--'"
    )

    # Multi-line
    assert sqlite_quote("hi\nthere") == "'hi\nthere'"
    assert sqlite_quote("hi\nthere\n") == "'hi\nthere\n'", "trailing new line"
    assert sqlite_quote("hi\nthere\\n") == "'hi\nthere\\n'", "escaped"

    assert sqlite_quote(" hi\nthere") == "' hi\nthere'"
    assert sqlite_quote(" hi\nthere \n ") == "' hi\nthere \n '"


def test_parse_cli_filter_value():
    assert parse_cli_filter_value("true") is True
    assert parse_cli_filter_value("7") == 7
    assert parse_cli_filter_value("1.5") == 1.5
    assert parse_cli_filter_value('["a","b"]') == ["a", "b"]
    assert parse_cli_filter_value("jsonl") == "jsonl"


def test_raise_cli_integrity_error_generic():
    with (
        pytest.raises(SystemExit) as exc,
        contextlib.redirect_stderr(io.StringIO()) as err_out,
    ):
        jsonlitedb._raise_cli_integrity_error(
            sqlite3.IntegrityError("FOREIGN KEY constraint failed"),
            command="insert",
        )
    assert exc.value.code == 1
    assert err_out.getvalue() == "Integrity error: FOREIGN KEY constraint failed\n"


def test_split_no_double_quotes():
    assert core.split_no_double_quotes("a.b.c", ".") == ["a", "b", "c"]
    assert core.split_no_double_quotes('a."b.c"', ".") == ["a", '"b.c"']
    assert core.split_no_double_quotes('"a.b.c"', ".") == ['"a.b.c"']
    assert core.split_no_double_quotes('"a.b.c', ".") == ['"a.b.c']
    assert core.split_no_double_quotes('"a.b"".c"', ".") == ['"a.b"".c"']
    assert core.split_no_double_quotes(r'"a.\"b\".c".d', ".") == [
        r'"a.\"b\".c"',
        "d",
    ]
    with pytest.raises(ValueError, match="Delimiter cannot be empty"):
        core.split_no_double_quotes("a.b", "")


def test_non_dicts():
    db = JSONLiteDB(":memory:")
    db.insert(["a", "b", "c"], ["A", "B", "C"])

    res = db.one(db.Q[1] == "B")
    assert res == db[2] == ["A", "B", "C"]
    assert hasattr(res, "rowid")
    assert hasattr(db[2], "rowid")

    assert db.one(db.Q[9] == "AA") is None

    db.insert("hi")
    assert list(db) == [["a", "b", "c"], ["A", "B", "C"], "hi"]
    assert db.get_by_rowid(3) == db[3] == "hi"

    res = db.one(db.Q[1] == "B")
    res.append("D")
    db.update(res)
    assert db[2] == ["A", "B", "C", "D"]

    db.create_index(tuple())
    db.add("hi")

    with pytest.raises(sqlite3.IntegrityError):
        db.create_index(db.Q, unique=True)
    db.delete_by_rowid(4)
    db.create_index(tuple(), unique=True)

    db.create_index(db.Q[1])
    assert db.indexes == {
        "ix_items_c3e97dd6": ["$"],
        "ix_items_c3e97dd6_UNIQUE": ["$"],
        "ix_items_ef1046ca": ["$[1]"],
    }
