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
    _raise_cli_integrity_error,
    cli,
    parse_cli_filter_value,
    sqlite_quote,
)


class MockArgv:
    def __init__(self, argv, *, stdin=None, shift=0):
        self.argv = argv
        self.shift = shift
        self.stdin = stdin

    def __enter__(self):
        self.argv_store = sys.argv
        argv = sys.argv[: self.shift]
        argv.extend(self.argv)
        sys.argv = argv

        if self.stdin:
            self.stdin_store = sys.stdin
            sys.stdin = self.stdin

        return self

    def __exit__(self, *_):
        sys.argv = self.argv_store

        if self.stdin:
            sys.stdin = self.stdin_store

        return self


def test_cli_insert_defaults_to_stdin():
    dbpath = "!!!TMP!!!defaultstdin.db"
    Path(dbpath).unlink(missing_ok=True)

    try:
        stdin = io.StringIO('{"name":"defaultstdin","ii":99}\n')
        with MockArgv(["insert", dbpath, "--table", "cli"], stdin=stdin, shift=1):
            cli()

        db = JSONLiteDB(dbpath, table="cli")
        try:
            assert db.query_one(name="defaultstdin")["ii"] == 99
        finally:
            db.close()
    finally:
        Path(dbpath).unlink(missing_ok=True)


def test_cli_import_and_add_wrappers():
    dbpath = "!!!TMP!!!import_add.db"
    infile = "!!!TMP!!!import_add.jsonl"
    Path(dbpath).unlink(missing_ok=True)
    Path(infile).unlink(missing_ok=True)

    try:
        Path(infile).write_text('{"name":"from_file","ii":1}\n')
        stdin = io.StringIO('{"name":"from_stdin","ii":2}\n')

        with MockArgv(
            ["import", dbpath, "--table", "cli", infile, "-"],
            stdin=stdin,
            shift=1,
        ):
            with contextlib.redirect_stderr(io.StringIO()) as err_out:
                cli()
        assert "positional insert inputs are deprecated" not in err_out.getvalue()

        db = JSONLiteDB(dbpath, table="cli")
        try:
            assert db.query_one(name="from_file")["ii"] == 1
            assert db.query_one(name="from_stdin")["ii"] == 2
        finally:
            db.close()

        with MockArgv(
            [
                "add",
                dbpath,
                "--table",
                "cli",
                "--json",
                '{"name":"from_add_flag","ii":3}',
                '{"name":"from_add_positional","ii":4}',
            ],
            shift=1,
        ):
            cli()

        db = JSONLiteDB(dbpath, table="cli")
        try:
            assert db.query_one(name="from_add_flag")["ii"] == 3
            assert db.query_one(name="from_add_positional")["ii"] == 4
        finally:
            db.close()
    finally:
        Path(dbpath).unlink(missing_ok=True)
        Path(infile).unlink(missing_ok=True)


def test_cli_insert_family_help_text():
    with MockArgv(["insert", "-h"], shift=1):
        with (
            pytest.raises(SystemExit) as exc,
            contextlib.redirect_stdout(io.StringIO()) as help_out,
        ):
            cli()
    assert exc.value.code == 0
    assert "Use `import` for the same behavior" in help_out.getvalue()

    with MockArgv(["import", "-h"], shift=1):
        with (
            pytest.raises(SystemExit) as exc,
            contextlib.redirect_stdout(io.StringIO()) as help_out,
        ):
            cli()
    assert exc.value.code == 0
    import_help = help_out.getvalue()
    assert "equivalent to" in import_help
    assert "`insert`" in import_help
    assert "or '-' for stdin" in import_help

    with MockArgv(["add", "-h"], shift=1):
        with (
            pytest.raises(SystemExit) as exc,
            contextlib.redirect_stdout(io.StringIO()) as help_out,
        ):
            cli()
    assert exc.value.code == 0
    add_help = help_out.getvalue()
    assert "shorthand for" in add_help
    assert "`insert --json" in add_help
    assert "Equivalent to repeating" in add_help


def test_cli_top_level_help_shows_read_write_command_lists():
    with MockArgv(["-h"], shift=1):
        with (
            pytest.raises(SystemExit) as exc,
            contextlib.redirect_stdout(io.StringIO()) as help_out,
        ):
            cli()
    assert exc.value.code == 0
    help_text = help_out.getvalue()
    assert "COMMAND (read-only):" in help_text
    assert "query, count, dump, indexes, stats" in help_text
    assert "COMMAND (write):" in help_text
    assert "insert, import, add, delete, patch, create-index, drop-index" in help_text


def test_cli_query_format_edges():
    dbpath = "!!!TMP!!!queryedges.db"
    Path(dbpath).unlink(missing_ok=True)

    try:
        db = JSONLiteDB(dbpath, table="cli")
        db.insert({"a": 1}, "scalar")
        db.close()

        with MockArgv(
            ["query", dbpath, "--table", "cli", "--json=[1,2,3]"],
            shift=1,
        ):
            with pytest.raises(
                ValueError, match="--json filters must decode to JSON objects"
            ):
                cli()

        # count should honor --limit and agree with row output size
        query_out = io.StringIO()
        with MockArgv(
            ["query", dbpath, "--table", "cli", "--format", "count", "--limit", "1"],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert query_out.getvalue().strip() == "1"
    finally:
        Path(dbpath).unlink(missing_ok=True)


def test_cli_table_env_default_and_override(monkeypatch):
    dbpath = "!!!TMP!!!clitableenv.db"
    Path(dbpath).unlink(missing_ok=True)

    try:
        monkeypatch.setenv("JSONLITEDB_CLI_TABLE", "envtable")

        with MockArgv(
            ["insert", dbpath, "--json", '{"name":"from_env","ii":1}'],
            shift=1,
        ):
            cli()

        env_db = JSONLiteDB(dbpath, table="envtable")
        assert env_db.count(name="from_env") == 1
        env_db.close()

        with MockArgv(
            [
                "insert",
                dbpath,
                "--table",
                "override",
                "--json",
                '{"name":"from_override","ii":2}',
            ],
            shift=1,
        ):
            cli()

        env_db = JSONLiteDB(dbpath, table="envtable")
        override_db = JSONLiteDB(dbpath, table="override")
        assert env_db.count(name="from_override") == 0
        assert override_db.count(name="from_override") == 1
        env_db.close()
        override_db.close()
    finally:
        Path(dbpath).unlink(missing_ok=True)


def test_cli_open_modes_missing_db():
    base = Path("!!!TMP!!!openmodes")
    base.mkdir(exist_ok=True)

    try:
        create_cmds = [
            ["insert", str(base / "create_insert.db"), "--json", '{"x":1}'],
            ["create-index", str(base / "create_index.db"), "x"],
        ]
        for argv in create_cmds:
            with MockArgv(argv, shift=1):
                cli()
            assert Path(argv[1]).exists()

        write_existing_cmds = [
            ["delete", str(base / "missing_delete.db"), "--allow-empty"],
            ["patch", str(base / "missing_patch.db"), "--patch", '{"x":1}'],
            ["drop-index", str(base / "missing_dropindex.db"), "--name", "ix_fake"],
        ]
        for argv in write_existing_cmds:
            with MockArgv(argv, shift=1):
                with (
                    pytest.raises(SystemExit) as exc,
                    contextlib.redirect_stderr(io.StringIO()) as err_out,
                ):
                    cli()
            assert exc.value.code == 1
            assert "database does not exist" in err_out.getvalue()
            assert not Path(argv[1]).exists()

        read_only_cmds = [
            ["query", str(base / "missing_query.db")],
            ["count", str(base / "missing_count.db")],
            ["dump", str(base / "missing_dump.db")],
            ["indexes", str(base / "missing_indexes.db")],
            ["stats", str(base / "missing_stats.db")],
        ]
        for argv in read_only_cmds:
            with MockArgv(argv, shift=1):
                with (
                    pytest.raises(SystemExit) as exc,
                    contextlib.redirect_stderr(io.StringIO()) as err_out,
                ):
                    cli()
            assert exc.value.code == 1
            assert "database does not exist" in err_out.getvalue()
            assert not Path(argv[1]).exists()
    finally:
        for item in base.glob("*.db"):
            item.unlink()
        base.rmdir()


def test_cli_dump_sql_branch(tmp_path):
    dbpath = tmp_path / "dump_sql.db"
    outfile = tmp_path / "dump.sql"
    db = JSONLiteDB(dbpath)  # default table 'items'
    db.insert({"a": 1})
    db.close()

    with MockArgv(["dump", str(dbpath), "--sql", "--output", str(outfile)], shift=1):
        cli()
    text = outfile.read_text()
    assert "CREATE TABLE items" in text


def test_cli_write_existing_unexpected_operational_error(monkeypatch):
    import importlib

    def fake_read_only(_dbpath, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    cli_module = importlib.import_module("jsonlitedb.cli")
    monkeypatch.setattr(
        cli_module.JSONLiteDB, "read_only", staticmethod(fake_read_only)
    )

    with MockArgv(["delete", "unused.db", "--allow-empty"], shift=1):
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            cli()


def test_raise_cli_integrity_error_non_unique_branch():
    err = sqlite3.IntegrityError("some other integrity error")
    with contextlib.redirect_stderr(io.StringIO()) as stderr_buf:
        with pytest.raises(SystemExit):
            _raise_cli_integrity_error(err, command="insert")
    assert "Integrity error: some other integrity error" in stderr_buf.getvalue()


@pytest.mark.parametrize(
    "argv",
    [
        ["import", "!!!TMP!!!argparse.db", "--table", "cli", "--bogus"],
        ["add", "!!!TMP!!!argparse.db", "--table", "cli", "--bogus"],
        ["query", "!!!TMP!!!argparse.db", "--table", "cli", "--bogus"],
    ],
)
def test_cli_rejects_unknown_option_in_parse_known_extras(argv):
    with MockArgv(argv, shift=1):
        with pytest.raises(SystemExit):
            cli()


def test_cli():
    # Need to test .json, .jsonl, and one-item-per-line json (likely mislabeled jsonl
    # or stdin)
    dbpath = "!!!TMP!!!my.db"
    file1 = "!!!TMP!!!file1.JSON"
    file2 = "!!!TMP!!!file2.jsonl"
    file3 = "!!!TMP!!!file3.jsonl"
    file4 = "!!!TMP!!!file4.ndjson"
    dump = "!!!TMP!!!dump.jsonl"
    dump2 = "!!!TMP!!!dump.sql"

    Path(dbpath).unlink(missing_ok=True)

    try:
        db = JSONLiteDB(dbpath, table="cli")
        db.create_index("name", unique=True)

        # one-item-per-line json
        stdin = io.StringIO()
        stdin.write("[\n")
        stdin.write(
            ",\n".join(
                [
                    json.dumps(item)
                    for item in [
                        {"name": "test1", "key0": "stdin", "ii": 0},
                        {"name": "test2", "key0": "stdin", "ii": 1},
                        {"name": "test3", "key0": "stdin", "ii": 2},
                    ]
                ]
            )
        )
        stdin.write("\n]")
        stdin.seek(0)

        with MockArgv(
            ["insert", "--table", "cli", dbpath, "-", "-"], stdin=stdin, shift=1
        ):
            cli()

        assert len(db) == 3

        # Regular json
        Path(file1).write_text(
            json.dumps(
                [
                    {"name": "test1", "key1": "json", "ii": 3},
                    {"name": "test4", "key1": "json", "ii": 4},
                    {"name": "test5", "key1": "json", "ii": 5},
                ]
            )
        )
        with MockArgv(
            ["insert", dbpath, file1, "--table", "cli", "--duplicates", "ignore"],
            shift=1,
        ):
            cli()

        assert len(db) == 5
        dup = db.query_one(name="test1")
        assert dup["key0"] == "stdin"
        assert dup["ii"] == 0
        assert "key1" not in dup

        # json lines
        with open(file2, "wt") as fp:
            print(
                json.dumps(
                    {"name": "test1", "key2": "jsonl", "ii": 6, "meta": {"rank": 1}}
                ),
                file=fp,
            )
            print(
                json.dumps(
                    {"name": "test7", "key2": "jsonl", "ii": 7, "meta": {"rank": 7}}
                ),
                file=fp,
            )
            print(
                json.dumps(
                    {"name": "test8", "key2": "jsonl", "ii": 8, "meta": {"rank": 8}}
                ),
                file=fp,
            )

        with MockArgv(
            ["insert", dbpath, file2, "--table", "cli", "--duplicates", "replace"],
            shift=1,
        ):
            cli()

        assert len(db) == 7
        dup = db.query_one(name="test1")
        assert dup["key2"] == "jsonl"
        assert dup["ii"] == 6
        assert "key0" not in dup
        assert "key1" not in dup

        with MockArgv(
            [
                "insert",
                dbpath,
                "--table",
                "cli",
                "--json",
                '{"name":"test7","ii":700}',
            ],
            shift=1,
        ):
            with (
                pytest.raises(SystemExit) as exc,
                contextlib.redirect_stderr(io.StringIO()) as err_out,
            ):
                cli()
        assert exc.value.code == 1
        err_text = err_out.getvalue()
        assert "Error: UNIQUE constraint violation." in err_text
        assert "Hint: use --duplicates ignore or --duplicates replace." in err_text
        assert "UNIQUE constraint failed" in err_text

        stdin = io.StringIO('{"name":"test7","ii":701}\n')
        with MockArgv(
            ["insert", dbpath, "--table", "cli", "--stdin"],
            stdin=stdin,
            shift=1,
        ):
            with (
                pytest.raises(SystemExit) as exc,
                contextlib.redirect_stderr(io.StringIO()) as err_out,
            ):
                cli()
        assert exc.value.code == 1
        assert "Error: UNIQUE constraint violation." in err_out.getvalue()

        with MockArgv(
            [
                "insert",
                dbpath,
                "--table",
                "cli",
                "--json",
                '{"name":"test9","key3":"inline","ii":9}',
            ],
            shift=1,
        ):
            cli()
        assert db.query_one(name="test9")["key3"] == "inline"

        stdin = io.StringIO('{"name":"test10","key3":"stdin-json","ii":10}')
        with MockArgv(
            [
                "insert",
                dbpath,
                "--table",
                "cli",
                "--stdin",
                "--stdin-format",
                "json",
            ],
            stdin=stdin,
            shift=1,
        ):
            cli()
        assert db.query_one(name="test10")["key3"] == "stdin-json"

        Path(file3).write_text(
            json.dumps({"name": "ordercheck", "src": "legacy", "ii": 2})
        )
        with MockArgv(
            [
                "insert",
                dbpath,
                file3,
                "--table",
                "cli",
                "--duplicates",
                "replace",
                "--json",
                '{"name":"ordercheck","src":"flag","ii":1}',
            ],
            shift=1,
        ):
            with contextlib.redirect_stderr(io.StringIO()) as err_out:
                cli()
        assert "positional insert inputs are deprecated" not in err_out.getvalue()
        assert db.query_one(name="ordercheck")["src"] == "legacy"

        with open(file4, "wt") as fp:
            print(json.dumps({"name": "test11", "key4": "ndjson", "ii": 11}), file=fp)
        with MockArgv(
            ["insert", dbpath, "--table", "cli", "--file", file4],
            shift=1,
        ):
            cli()
        assert db.query_one(name="test11")["key4"] == "ndjson"

        with MockArgv(["dump", dbpath, "--table", "cli", "--output", dump], shift=1):
            cli()
        dumpout = Path(dump).read_text().strip()
        assert len(dumpout.split("\n")) == 11

        with MockArgv(["dump", dbpath, "--sql", "--output", dump2], shift=1):
            cli()

        with MockArgv(
            ["create-index", dbpath, "--table", "cli", "key2", "meta,rank"],
            shift=1,
        ):
            cli()
        assert ['$."key2"', '$."meta"."rank"'] in db.indexes.values()

        with MockArgv(["create-index", dbpath, "--table", "cli", "ii"], shift=1):
            cli()
        assert ['$."ii"'] in db.indexes.values()

        query_out = io.StringIO()
        with MockArgv(["indexes", dbpath, "--table", "cli"], shift=1):
            with contextlib.redirect_stdout(query_out):
                cli()
        indexes_text = query_out.getvalue()
        assert "ix_cli_" in indexes_text
        assert '$."ii"' in indexes_text

        name_to_drop = next(
            name for name, paths in db.indexes.items() if paths == ['$."ii"']
        )
        with MockArgv(
            ["drop-index", dbpath, "--table", "cli", "--name", name_to_drop], shift=1
        ):
            cli()
        assert ['$."ii"'] not in db.indexes.values()

        with MockArgv(
            ["create-index", dbpath, "--table", "cli", "--unique", "ii"],
            shift=1,
        ):
            with (
                pytest.raises(SystemExit) as exc,
                contextlib.redirect_stderr(io.StringIO()) as err_out,
            ):
                cli()
        assert exc.value.code == 1
        assert "Error: UNIQUE constraint violation." in err_out.getvalue()
        assert "Hint:" not in err_out.getvalue()

        unique_name = next(
            name for name, paths in db.indexes.items() if name.endswith("_UNIQUE")
        )
        with MockArgv(
            ["drop-index", dbpath, "--table", "cli", "--name", unique_name], shift=1
        ):
            cli()
        assert unique_name not in db.indexes

        with MockArgv(
            ["drop-index", dbpath, "key2", "meta,rank", "--table", "cli"], shift=1
        ):
            cli()
        assert ['$."key2"', '$."meta"."rank"'] not in db.indexes.values()

        with MockArgv(["drop-index", dbpath, "--table", "cli"], shift=1):
            with pytest.raises(ValueError, match="requires --name"):
                cli()

        with MockArgv(["drop-index", dbpath, ",", "--table", "cli"], shift=1):
            with pytest.raises(ValueError, match="Invalid index path"):
                cli()

        with MockArgv(["create-index", dbpath, ",", "--table", "cli"], shift=1):
            with pytest.raises(ValueError, match="Invalid index path"):
                cli()

        query_out = io.StringIO()
        with MockArgv(["indexes", dbpath, "--table", "cli"], shift=1):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert query_out.getvalue() == "No indexes\n"

        query_out = io.StringIO()
        with MockArgv(["count", dbpath, "key2=jsonl", "--table", "cli"], shift=1):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert query_out.getvalue().strip() == "3"

        query_out = io.StringIO()
        with MockArgv(["count", dbpath, "--table", "cli"], shift=1):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert query_out.getvalue().strip() == "11"

        with MockArgv(
            [
                "patch",
                dbpath,
                "name=test7",
                "--table",
                "cli",
                '--patch={"patched":true,"role":null}',
            ],
            shift=1,
        ):
            cli()
        patched = db.query_one(name="test7")
        assert patched["patched"] is True
        assert "role" not in patched

        with MockArgv(
            ["patch", dbpath, "name=test7", "--table", "cli", "--patch", "[1,2,3]"],
            shift=1,
        ):
            with pytest.raises(
                ValueError, match="--patch must decode to a JSON object"
            ):
                cli()

        with MockArgv(
            [
                "patch",
                dbpath,
                "--table",
                "cli",
                '--patch={"json_filter":true}',
                '--json={"name":"test8"}',
            ],
            shift=1,
        ):
            cli()
        assert db.query_one(name="test8")["json_filter"] is True

        with MockArgv(
            [
                "patch",
                dbpath,
                "$.meta.rank=7",
                "--table",
                "cli",
                '--patch={"path_filter":true}',
            ],
            shift=1,
        ):
            cli()
        assert db.query_one(name="test7")["path_filter"] is True

        with MockArgv(["patch", "-h"], shift=1):
            with (
                pytest.raises(SystemExit) as exc,
                contextlib.redirect_stdout(io.StringIO()) as help_out,
            ):
                cli()
        assert exc.value.code == 0
        assert "keys set to null are removed" in help_out.getvalue()

        query_out = io.StringIO()
        with MockArgv(["stats", dbpath, "--table", "cli"], shift=1):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert "Indexes: none" in query_out.getvalue()

        with MockArgv(["create-index", dbpath, "--table", "cli", "patched"], shift=1):
            cli()
        query_out = io.StringIO()
        with MockArgv(["stats", dbpath, "--table", "cli"], shift=1):
            with contextlib.redirect_stdout(query_out):
                cli()
        stats_text = query_out.getvalue()
        assert "Rows: 11" in stats_text
        assert "Page Size:" in stats_text
        assert "Indexes:" in stats_text

        query_out = io.StringIO()
        with MockArgv(["query", dbpath, "name=test7", "--table", "cli"], shift=1):
            with contextlib.redirect_stdout(query_out):
                cli()
        query_rows = [
            json.loads(line) for line in query_out.getvalue().strip().splitlines()
        ]
        assert query_rows == [
            {
                "name": "test7",
                "key2": "jsonl",
                "ii": 7,
                "meta": {"rank": 7},
                "patched": True,
                "path_filter": True,
            }
        ]

        query_out = io.StringIO()
        with MockArgv(
            [
                "query",
                dbpath,
                "key2 = jsonl",  # Spaces testing too
                "--table",
                "cli",
                "--orderby=-ii",
                "--limit",
                "2",
            ],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        query_rows = [
            json.loads(line) for line in query_out.getvalue().strip().splitlines()
        ]
        assert [row["ii"] for row in query_rows] == [8, 7]

        query_out = io.StringIO()
        with MockArgv(
            [
                "query",
                dbpath,
                "key2=jsonl",
                "--table",
                "cli",
                "--orderby=-meta,rank",
                "--limit",
                "2",
            ],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        query_rows = [
            json.loads(line) for line in query_out.getvalue().strip().splitlines()
        ]
        assert [row["name"] for row in query_rows] == ["test8", "test7"]

        query_out = io.StringIO()
        with MockArgv(
            ["query", dbpath, "$.meta.rank=7", "--table", "cli"],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        query_rows = [
            json.loads(line) for line in query_out.getvalue().strip().splitlines()
        ]
        assert [row["name"] for row in query_rows] == ["test7"]

        query_out = io.StringIO()
        with MockArgv(
            ["query", dbpath, "--table", "cli", '--json={"name":"test7"}'],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        query_rows = [
            json.loads(line) for line in query_out.getvalue().strip().splitlines()
        ]
        assert [row["name"] for row in query_rows] == ["test7"]

        query_out = io.StringIO()
        with MockArgv(
            ["query", dbpath, "key2=jsonl", "--table", "cli", "--format", "count"],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert query_out.getvalue().strip() == "3"

        query_out = io.StringIO()
        with MockArgv(
            ["query", dbpath, "name=test7", "--table", "cli", "--format", "json"],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        query_rows = json.loads(query_out.getvalue().strip())
        assert [row["name"] for row in query_rows] == ["test7"]

        query_out = io.StringIO()
        with MockArgv(
            [
                "query",
                dbpath,
                "key2=jsonl",
                "--table",
                "cli",
                "--format",
                "json",
                "--limit",
                "2",
            ],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        query_json = query_out.getvalue()
        assert query_json.startswith("[\n")
        assert query_json.endswith("\n]\n")
        assert not query_json.startswith("[\n,")
        assert ",\n" in query_json
        query_rows = json.loads(query_json)
        assert len(query_rows) == 2

        query_out = io.StringIO()
        with MockArgv(
            [
                "query",
                dbpath,
                "name=does-not-exist",
                "--table",
                "cli",
                "--format",
                "json",
            ],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert query_out.getvalue() == "[\n\n]\n"
        assert json.loads(query_out.getvalue()) == []

        # "line-like" JSON encoder should be compact (no spaces around separators)
        query_out = io.StringIO()
        with MockArgv(
            ["query", dbpath, "name=test7", "--table", "cli"],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert '"meta":{"rank":7}' in query_out.getvalue()

        # count and limited query row count should match
        query_out = io.StringIO()
        with MockArgv(
            [
                "query",
                dbpath,
                "key2=jsonl",
                "--table",
                "cli",
                "--format",
                "count",
                "--limit",
                "2",
            ],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert query_out.getvalue().strip() == "2"

        query_out = io.StringIO()
        with MockArgv(
            ["query", dbpath, "key2=jsonl", "--table", "cli", "--limit", "2"],
            shift=1,
        ):
            with contextlib.redirect_stdout(query_out):
                cli()
        assert len(query_out.getvalue().strip().splitlines()) == 2

        with MockArgv(["query", "-h"], shift=1):
            with (
                pytest.raises(SystemExit) as exc,
                contextlib.redirect_stdout(io.StringIO()) as help_out,
            ):
                cli()
        assert exc.value.code == 0
        help_text = help_out.getvalue()
        assert "Examples:" in help_text
        assert "jsonlitedb query my.db name=George" in help_text
        assert '--json=\'{"active": true, "rank": 7}\'' in help_text
        assert "--orderby=last --orderby=-born" in help_text
        assert (
            "supports simple equality filters and path-based sorting only" in help_text
        )

        with MockArgv(["query", dbpath, "badfilter", "--table", "cli"], shift=1):
            with pytest.raises(ValueError):
                cli()

        with MockArgv(["delete", dbpath, "--table", "cli"], shift=1):
            with (
                pytest.raises(SystemExit) as exc,
                contextlib.redirect_stderr(io.StringIO()) as err_out,
            ):
                cli()
        assert exc.value.code == 1
        assert (
            "Error: refusing to delete all rows without filters." in err_out.getvalue()
        )
        assert "--allow-empty" in err_out.getvalue()
        assert len(db) == 11

        with MockArgv(
            ["delete", dbpath, "--table", "cli", '--json={"name":"test11"}'], shift=1
        ):
            cli()
        assert db.count(name="test11") == 0

        with MockArgv(["delete", dbpath, "--table", "cli", "--allow-empty"], shift=1):
            cli()
        assert len(db) == 0

    finally:
        for item in Path(".").glob("!!!*"):
            item.unlink()
