#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import sqlite3
import sys
from textwrap import dedent

from .jsonlitedb import JSONLiteDB, __version__

CLI_TABLE_ENV = "JSONLITEDB_CLI_TABLE"


class _AppendInsertInput(argparse.Action):
    """
    Record insert-family input sources in the exact order they appear on argv.

    Insert-family commands can combine `--stdin`, `--file`, and `--json`.
    This action appends `(source_kind, payload)` tuples so execution can follow
    command-line order deterministically.

    Notes
    -----
    `insert` positional file inputs are a legacy compatibility path and are
    appended after all flagged inputs.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        inputs = getattr(namespace, self.dest, None)
        if inputs is None:
            inputs = []
        kind = option_string.lstrip("-")
        payload = None if values == [] else values
        inputs.append((kind, payload))
        setattr(namespace, self.dest, inputs)


def _json_dump_line(item):
    """
    Encode an item as compact single-line JSON for CLI streaming output.
    """
    return json.dumps(item, ensure_ascii=False, separators=(",", ":"))


def parse_cli_filter_value(text):
    """
    Parse CLI filter text as JSON, falling back to raw string on parse failure.

    Parameters
    ----------
    text : str
        Raw filter value from command-line input.

    Returns
    -------
    object
        Parsed JSON value when `text` is valid JSON, otherwise the original
        string.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _raise_cli_integrity_error(exc, *, command):
    """
    Convert SQLite integrity errors into user-facing CLI output and exit.

    Parameters
    ----------
    exc : sqlite3.IntegrityError
        Original SQLite exception.
    command : str
        CLI subcommand being executed (for context-specific hints).

    Raises
    ------
    SystemExit
        Always raises with exit code 1 after writing an error message.
    """
    message = str(exc).strip()
    if "UNIQUE constraint failed" in message:
        lines = ["Error: UNIQUE constraint violation."]
        match = re.search(r"index '([^']+)'", message)
        if match:
            lines.append(f"Index: {match.group(1)}")
        if command == "insert":
            lines.append("Hint: use --duplicates ignore or --duplicates replace.")
        lines.append(f"SQLite: {message}")
        sys.stderr.write("\n".join(lines) + "\n")
        raise SystemExit(1) from exc

    sys.stderr.write(f"Integrity error: {message}\n")
    raise SystemExit(1) from exc


def cli():
    """
    Run the JSONLiteDB command-line interface.

    This function parses argv, executes the selected subcommand, writes
    command output to stdout/stderr, and exits with status code semantics
    suitable for shell scripting.
    """
    default_table = os.environ.get(CLI_TABLE_ENV) or "items"
    desc = dedent(
        f"""
        Command-line tool for inserting JSON/JSONL into a JSONLiteDB (SQLite) file.

        Input is treated as JSON Lines (one JSON value per line). Files ending in
        .json are parsed as full JSON; .jsonl and .ndjson files are read line-by-line.
        `insert` and `import` are equivalent for file/stdin ingestion.
        `add` is shorthand for `insert --json`.

        Default table comes from ${CLI_TABLE_ENV} (fallback: 'items').
        Use --table to override for any command.
        """
    )

    parser = argparse.ArgumentParser(
        description=desc, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    global_parent = argparse.ArgumentParser(add_help=False)
    global_parent.add_argument(
        "--table",
        default=default_table,
        metavar="NAME",
        help=(
            "Table name. Defaults to %(default)r, or set "
            f"${CLI_TABLE_ENV}. --table always overrides."
        ),
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
        metavar="COMMAND",
        description=dedent(
            """
            Read-only commands: query, count, dump, indexes, stats
            Write commands: insert, import, add, delete, patch, create-index, drop-index

            These commands offer many options but use the Python JSONLiteDB module or
            direct sqlite3 for full manipulation.

            Run `%(prog)s <command> -h` for help.
            """
        ),
    )

    def _add_insert_family_parser(command, *, help_text, description, positional_mode):
        cmd_parser = subparser.add_parser(
            command,
            parents=[global_parent],
            help=help_text,
            description=description,
        )

        cmd_parser.add_argument(
            "--duplicates",
            choices={"replace", "ignore"},
            default=False,
            help=(
                'How to handle "UNIQUE" constraint conflicts. If omitted, conflicts '
                "raise an error."
            ),
        )

        cmd_parser.add_argument("dbpath", help="JSONLiteDB file")

        if positional_mode == "legacy_files":
            group_desc = dedent(
                """
                Input sources are processed in command-line order for flagged inputs.
                Legacy positional file inputs are processed after all flagged inputs.
                """
            )
        elif positional_mode == "json_items":
            group_desc = dedent(
                """
                Input sources are processed in command-line order for flagged inputs.
                Positional JSON_ITEM values are equivalent to repeating --json JSON_ITEM
                and are processed after all flagged inputs.
                """
            )
        else:
            group_desc = dedent(
                """
                Input sources are processed in command-line order for flagged inputs.
                Positional file inputs are processed after all flagged inputs.
                """
            )

        input_group = cmd_parser.add_argument_group("Input sources", group_desc)
        input_group.add_argument(
            "--stdin",
            nargs=0,
            action=_AppendInsertInput,
            dest="inputs",
            help="Read JSON or JSONL from stdin. See --stdin-format",
        )
        input_group.add_argument(
            "--file",
            action=_AppendInsertInput,
            dest="inputs",
            metavar="PATH",
            help="""
                JSON/JSONL file input. Files ending in '.jsonl' or '.ndjson'
                are read line-by-line.
                Files ending in '.json' are loaded as a full JSON value (single
                item or array of items).
            """,
        )
        input_group.add_argument(
            "--json",
            action=_AppendInsertInput,
            dest="inputs",
            metavar="ITEM",
            help="""Single JSON item to add. Example: --json '{"first":"Jim","last":"Kim"}'""",
        )
        input_group.add_argument(
            "--stdin-format",
            choices=("json", "jsonlines"),
            default="jsonlines",
            help="Format to expect for --stdin. Default: '%(default)s'",
        )

        if positional_mode == "json_items":
            cmd_parser.add_argument(
                "json_inputs",
                nargs="*",
                metavar="JSON_ITEM",
                help=(
                    "Positional JSON item(s). Equivalent to repeating --json "
                    "JSON_ITEM."
                ),
            )
        else:
            cmd_parser.add_argument(
                "legacy_inputs",
                nargs="*",
                metavar="FILE_OR_DASH",
                help=(
                    """
                    Legacy positional input(s) for backward compatibility.
                    Prefer `import` or --file/--stdin. Positional inputs are processed
                    after all flagged inputs.
                    """
                    if positional_mode == "legacy_files"
                    else """
                    Positional input file(s), or '-' for stdin. Positional inputs are
                    processed after all flagged inputs.
                    """
                ),
            )

    _add_insert_family_parser(
        "insert",
        help_text="insert JSON into a JSONLiteDB database",
        description=(
            "Insert JSON/JSONL data into a database. "
            "Use `import` for the same behavior with preferred positional file input."
        ),
        positional_mode="legacy_files",
    )
    _add_insert_family_parser(
        "import",
        help_text="same as insert (w/o deprecated positional input)",
        description=(
            "Import JSON/JSONL data into a database. "
            "This command is equivalent to `insert`, and is the preferred command "
            "for positional file inputs."
        ),
        positional_mode="files",
    )
    _add_insert_family_parser(
        "add",
        help_text="shorthand for insert --json (i.e., positional input mode)",
        description=(
            "Add JSON item(s) to a database. "
            "Positional JSON_ITEM values are shorthand for `insert --json JSON_ITEM`."
        ),
        positional_mode="json_items",
    )

    query_desc = dedent(
        """
        Query rows and emit matching JSON Lines.

        Filters are limited to equality expressions and are combined with AND.
        """
    )
    query_epilog = dedent(
        """
        Examples:
          jsonlitedb query my.db name=George
          jsonlitedb query my.db '$.meta.rank=7' active=true --limit 5
          jsonlitedb query my.db --json='{"active": true, "rank": 7}'
          jsonlitedb query my.db --orderby=last --orderby=-born
          jsonlitedb query my.db key2=myquery --orderby=-meta,rank
          jsonlitedb query my.db active=true rank=7 score=1.5 tags='["a","b"]'

        Notes:
          `query` supports simple equality filters and path-based sorting only.
          Use Python `JSONLiteDB.query(...)` for OR/NOT, inequalities, LIKE/GLOB/REGEXP,
          and other advanced query composition.
        """
    )
    query = subparser.add_parser(
        "query",
        help="query database and emit JSONL",
        parents=[global_parent],
        description=query_desc,
        epilog=query_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    query.add_argument("dbpath", help="JSONLiteDB file")
    query.add_argument(
        "filters",
        nargs="*",
        help="Filters in key=value form (values parsed as JSON when possible)",
    )
    query.add_argument(
        "--json",
        action="append",
        default=None,
        metavar="OBJECT",
        help=(
            "JSON object equality filter; repeatable. Each object is expanded "
            "into ANDed key=value filters."
        ),
    )
    query.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Limit results to N rows",
    )
    query.add_argument(
        "--format",
        choices=("jsonl", "json", "count"),
        default="jsonl",
        help="""
            Output format.
            Note that 'json' still does one item per line but is valid JSON as a whole.
            Default: '%(default)s'""",
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

    count = subparser.add_parser(
        "count",
        help="count matching rows",
        parents=[global_parent],
        description="Count rows matching equality filters.",
    )
    count.add_argument("dbpath", help="JSONLiteDB file")
    count.add_argument(
        "filters",
        nargs="*",
        help="Filters in key=value form (values parsed as JSON when possible)",
    )
    count.add_argument(
        "--json",
        action="append",
        default=None,
        metavar="OBJECT",
        help=(
            "JSON object equality filter; repeatable. Each object is expanded "
            "into ANDed key=value filters."
        ),
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

    indexes = subparser.add_parser(
        "indexes",
        help="list indexes",
        parents=[global_parent],
        description="List indexes for the selected table.",
    )
    indexes.add_argument("dbpath", help="JSONLiteDB file")

    stats = subparser.add_parser(
        "stats",
        help="show database stats",
        parents=[global_parent],
        description="Show human-readable row/index/storage stats for a table.",
    )
    stats.add_argument("dbpath", help="JSONLiteDB file")

    delete_desc = dedent(
        """
        Delete rows matching equality filters.

        Safety: an empty filter set is rejected unless --allow-empty is provided.
        """
    )
    delete = subparser.add_parser(
        "delete",
        help="delete matching rows",
        parents=[global_parent],
        description=delete_desc,
    )
    delete.add_argument("dbpath", help="JSONLiteDB file")
    delete.add_argument(
        "filters",
        nargs="*",
        help="Filters in key=value form (values parsed as JSON when possible)",
    )
    delete.add_argument(
        "--json",
        action="append",
        default=None,
        metavar="OBJECT",
        help=(
            "JSON object equality filter; repeatable. Each object is expanded "
            "into ANDed key=value filters."
        ),
    )
    delete.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow delete with no filters (deletes all rows in the table).",
    )

    create_index = subparser.add_parser(
        "create-index",
        help="create a JSON index",
        parents=[global_parent],
        description=(
            "Create an index on one or more JSON paths. Use commas for nested "
            "keys, e.g. 'meta,rank'."
        ),
    )
    create_index.add_argument("dbpath", help="JSONLiteDB file")
    create_index.add_argument(
        "paths",
        nargs="+",
        help=(
            "Index path(s): key, $.json.path, or comma-separated nested keys "
            "(e.g., parent,child)."
        ),
    )
    create_index.add_argument(
        "--unique",
        action="store_true",
        help="Create a UNIQUE index.",
    )
    drop_index = subparser.add_parser(
        "drop-index",
        help="drop a JSON index",
        parents=[global_parent],
        description=(
            "Drop indexes by name and/or by JSON paths. Use commas for nested keys, "
            "e.g. 'meta,rank'."
        ),
    )
    drop_index.add_argument("dbpath", help="JSONLiteDB file")
    drop_index.add_argument(
        "paths",
        nargs="*",
        help=(
            "Index path(s): key, $.json.path, or comma-separated nested keys "
            "(e.g., parent,child)."
        ),
    )
    drop_index.add_argument(
        "--name",
        action="append",
        default=None,
        help="Index name to drop; repeatable.",
    )
    drop_index.add_argument(
        "--unique",
        action="store_true",
        help="Target the UNIQUE index variant for path-based drops.",
    )

    patch = subparser.add_parser(
        "patch",
        help="apply JSON Merge Patch to matching rows",
        parents=[global_parent],
        description=dedent(
            """
            Apply a JSON Merge Patch document to matching rows.

            Important:
              In JSON Merge Patch, keys set to null are removed.
              This means you cannot set a value to JSON null with this command.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    patch.add_argument("dbpath", help="JSONLiteDB file")
    patch.add_argument(
        "--patch",
        required=True,
        metavar="PATCH_OBJECT",
        help="JSON object patch document. Example: --patch '{\"active\":true}'",
    )
    patch.add_argument(
        "filters",
        nargs="*",
        help="Filters in key=value form (values parsed as JSON when possible)",
    )
    patch.add_argument(
        "--json",
        action="append",
        default=None,
        metavar="OBJECT",
        help=(
            "JSON object equality filter; repeatable. Each object is expanded "
            "into ANDed key=value filters."
        ),
    )

    if len(sys.argv) == 2 and sys.argv[1] in {"-h", "--help"}:
        parser.print_help()
        sys.stdout.write(
            dedent(
                """

                COMMAND (read-only):
                  query, count, dump, indexes, stats

                COMMAND (write):
                  insert, import, add, delete, patch, create-index, drop-index
                """
            )
        )
        raise SystemExit(0)

    args = parser.parse_args()

    create_if_missing_commands = {"insert", "import", "add", "create-index"}
    write_existing_commands = {"delete", "patch", "drop-index"}
    read_only_existing_commands = {"query", "count", "dump", "indexes", "stats"}

    def _db_missing_message(command, dbpath):
        sys.stderr.write(
            f"Error: database does not exist for '{command}': {dbpath}\n"
            "Create it first with 'insert' or 'create-index'.\n"
        )

    if args.command in create_if_missing_commands:
        db = JSONLiteDB(args.dbpath, table=args.table)
    elif args.command in read_only_existing_commands:
        try:
            db = JSONLiteDB.read_only(args.dbpath, table=args.table)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "unable to open database file" in msg:
                _db_missing_message(args.command, args.dbpath)
                raise SystemExit(1) from exc
            raise
    elif args.command in write_existing_commands:
        try:
            probe = JSONLiteDB.read_only(args.dbpath, table=args.table)
            probe.close()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "unable to open database file" in msg:
                _db_missing_message(args.command, args.dbpath)
                raise SystemExit(1) from exc
            raise
        db = JSONLiteDB(args.dbpath, table=args.table)
    else:
        raise ValueError(
            f"Unknown command category for {args.command!r}"
        )  # pragma: no cover

    def _parse_cli_eq_filters(filters, json_filters):
        eq_args = []
        eq_kwargs = {}

        def _add_eq_filter(key, val):
            if key.startswith("$"):
                eq_args.append({key: val})
            else:
                eq_kwargs[key] = val

        for filt in filters:
            if "=" not in filt:
                raise ValueError(f"Invalid filter {filt!r}. Use key=value.")
            key, val = tuple(kv.strip() for kv in filt.split("=", 1))
            val = parse_cli_filter_value(val)
            _add_eq_filter(key, val)

        for json_filter in json_filters or []:
            filt = json.loads(json_filter)
            if not isinstance(filt, dict):
                raise ValueError("--json filters must decode to JSON objects")
            for key, val in filt.items():
                _add_eq_filter(str(key), val)

        return eq_args, eq_kwargs

    if args.command in {"insert", "import", "add"}:

        def _insert_parsed_json(value):
            try:
                if isinstance(value, list):
                    db.insertmany(value, duplicates=args.duplicates)
                else:
                    db.insert(value, duplicates=args.duplicates)
            except sqlite3.IntegrityError as exc:
                _raise_cli_integrity_error(exc, command="insert")

        def _insert_jsonlines(fp):
            lines = (line.strip() for line in fp)
            lines = (line for line in lines if line not in "[]")
            lines = (line.rstrip(",") for line in lines)
            try:
                db.insertmany(lines, _dump=False, duplicates=args.duplicates)
            except sqlite3.IntegrityError as exc:
                _raise_cli_integrity_error(exc, command="insert")

        inputs = list(args.inputs or [])
        if args.command == "add":
            inputs.extend([("json", item) for item in (args.json_inputs or [])])

        legacy_inputs = list(getattr(args, "legacy_inputs", []) or [])
        if legacy_inputs:
            inputs.extend([("legacy", item) for item in legacy_inputs])
        if not inputs:
            inputs = [("stdin", None)]

        read_stdin = False
        for source, payload in inputs:
            if source == "json":
                _insert_parsed_json(json.loads(payload))
                continue

            if source == "stdin" or (source == "legacy" and payload == "-"):
                if read_stdin:
                    continue
                read_stdin = True
                if args.stdin_format == "json":
                    _insert_parsed_json(json.load(sys.stdin))
                else:
                    _insert_jsonlines(sys.stdin)
                continue

            file = payload
            if file.lower().endswith(".json"):
                with open(file, "rt") as fp:
                    _insert_parsed_json(json.load(fp))
            else:
                with open(file, "rt") as fp:
                    _insert_jsonlines(fp)
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
        eq_args, eq_kwargs = _parse_cli_eq_filters(args.filters, args.json)

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

        if args.format == "count":
            count_res = db.count(*eq_args, **eq_kwargs, **q_kwargs)
            sys.stdout.write(str(count_res) + "\n")
            db.close()
            return

        if args.format == "json":
            sys.stdout.write("[\n")
        first = True
        for item in db.query(*eq_args, **eq_kwargs, **q_kwargs):
            if args.format == "jsonl":
                sys.stdout.write(_json_dump_line(item) + "\n")
            else:
                if not first:
                    sys.stdout.write(",\n")
                sys.stdout.write(_json_dump_line(item))
                first = False
        if args.format == "json":
            sys.stdout.write("\n]\n")
    elif args.command == "delete":
        eq_args, eq_kwargs = _parse_cli_eq_filters(args.filters, args.json)
        if not args.allow_empty and not (eq_args or eq_kwargs):
            sys.stderr.write(
                "Error: refusing to delete all rows without filters.\n"
                "Add one or more filters (e.g. name=Paul) or use --allow-empty.\n"
            )
            raise SystemExit(1)
        db.remove(*eq_args, **eq_kwargs)
    elif args.command == "create-index":
        paths = []
        for item in args.paths:
            if "," in item:
                parts = tuple(part.strip() for part in item.split(",") if part.strip())
                if not parts:
                    raise ValueError("Invalid index path: empty comma-separated item")
                paths.append(parts)
            else:
                paths.append(item)
        try:
            db.create_index(*paths, unique=args.unique)
        except sqlite3.IntegrityError as exc:
            _raise_cli_integrity_error(exc, command="create-index")
    elif args.command == "drop-index":
        dropped = False
        for name in args.name or []:
            db.drop_index_by_name(name)
            dropped = True

        if args.paths:
            paths = []
            for item in args.paths:
                if "," in item:
                    parts = tuple(
                        part.strip() for part in item.split(",") if part.strip()
                    )
                    if not parts:
                        raise ValueError(
                            "Invalid index path: empty comma-separated item"
                        )
                    paths.append(parts)
                else:
                    paths.append(item)
            db.drop_index(*paths, unique=args.unique)
            dropped = True

        if not dropped:
            raise ValueError("drop-index requires --name and/or one or more paths")
    elif args.command == "indexes":
        index_map = db.indexes
        if not index_map:
            sys.stdout.write("No indexes\n")
        for name, paths in index_map.items():
            suffix = " [UNIQUE]" if name.endswith("_UNIQUE") else ""
            sys.stdout.write(f"{name}{suffix}: {', '.join(paths)}\n")
    elif args.command == "patch":
        patchitem = json.loads(args.patch)
        if not isinstance(patchitem, dict):
            raise ValueError("--patch must decode to a JSON object")
        eq_args, eq_kwargs = _parse_cli_eq_filters(args.filters, args.json)
        db.patch(patchitem, *eq_args, **eq_kwargs)
    elif args.command == "count":
        eq_args, eq_kwargs = _parse_cli_eq_filters(args.filters, args.json)
        sys.stdout.write(str(db.count(*eq_args, **eq_kwargs)) + "\n")
    elif args.command == "stats":
        stats_obj = db.stats()
        sys.stdout.write(f"Database: {stats_obj['dbpath']}\n")
        sys.stdout.write(f"Table: {stats_obj['table']}\n")
        sys.stdout.write(f"Rows: {stats_obj['rows']}\n")
        sys.stdout.write(f"Page Size: {stats_obj['page_size']}\n")
        sys.stdout.write(f"Page Count: {stats_obj['page_count']}\n")
        sys.stdout.write(f"Freelist Count: {stats_obj['freelist_count']}\n")
        sys.stdout.write(f"Bytes: {stats_obj['bytes']}\n")
        if not stats_obj["indexes"]:
            sys.stdout.write("Indexes: none\n")
        else:
            sys.stdout.write("Indexes:\n")
            for name, paths in stats_obj["indexes"].items():
                suffix = " [UNIQUE]" if name.endswith("_UNIQUE") else ""
                sys.stdout.write(f"  - {name}{suffix}: {', '.join(paths)}\n")

    db.close()


if __name__ == "__main__":  # pragma: no cover
    cli()
