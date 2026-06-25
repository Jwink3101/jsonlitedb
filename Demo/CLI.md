<!-- md-demo
runtime: bash
setup: |
    set +e
    rm -rf my.db 1> /dev/null 2>&1
    export JSONLITEDB_DISABLE_META=true # metadata in the file causes churn. Disable it for this demo
-->

# CLI Usage

While JSONLiteDB is *fundamentally* made to be a Python module, it comes with some minimal CLI tools to add, query, and dump the database. It does not currently support deleting rows, creating indexes, building advanced queries, etc. though those all may come in the future.

**Note**: This is a *shell* notebook

Clear a temp database so we are starting fresh

```bash exe
jsonlitedb --version
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
jsonlitedb-0.5.1
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb insert my.db --stdin <<JSONL
    {"first": "John", "last": "Lennon", "born": 1940, "role": "guitar"}
    {"first": "Paul", "last": "McCartney", "born": 1942, "role": "bass"}
    {"first": "George", "last": "Harrison", "born": 1943, "role": "guitar"}
    {"first": "Ringo", "last": "Starr", "born": 1940, "role": "drums"}
JSONL

jsonlitedb query my.db --format count
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
4
```
<!-- md-demo: result end -->
Other ways to insert

```bash exe
jsonlitedb insert my.db --json ' {"first": "George", "last": "Martin", "born": 1926, "role": "producer"}'

jsonlitedb query my.db --format count
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
5
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb query my.db first=George
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{"first":"George","last":"Harrison","born":1943,"role":"guitar"}
{"first":"George","last":"Martin","born":1926,"role":"producer"}
```
<!-- md-demo: result end -->
You can also output in json instead of jsonlines. Note that it tries to still keep one item per line:

```bash exe
jsonlitedb query my.db first=George --format json --orderby born
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
[
{"first":"George","last":"Martin","born":1926,"role":"producer"},
{"first":"George","last":"Harrison","born":1943,"role":"guitar"}
]
```
<!-- md-demo: result end -->
More advanced ordering.

**Note**: You must either escape the negative (`--orderby "\-born"`) or use an `=` (`--orderby=-born`)

```bash exe
jsonlitedb query my.db --orderby first --orderby=-born
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{"first":"George","last":"Harrison","born":1943,"role":"guitar"}
{"first":"George","last":"Martin","born":1926,"role":"producer"}
{"first":"John","last":"Lennon","born":1940,"role":"guitar"}
{"first":"Paul","last":"McCartney","born":1942,"role":"bass"}
{"first":"Ringo","last":"Starr","born":1940,"role":"drums"}
```
<!-- md-demo: result end -->
Add an index on first and last for faster queries. Make it unique then demonstrate how it works

```bash exe
jsonlitedb create-index my.db first last --unique
```

```bash exe
jsonlitedb insert my.db \
    --json '{"first":"Paul","last":"McCartney","role":"IMPOSTER"}' || echo "Command failed, continuing"
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
Error: UNIQUE constraint violation.
Index: ix_items_250e4243_UNIQUE
Hint: use --duplicates ignore or --duplicates replace.
SQLite: UNIQUE constraint failed: index 'ix_items_250e4243_UNIQUE'
Command failed, continuing
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb insert my.db \
    --duplicates ignore \
    --json '{"first":"Paul","last":"McCartney","role":"IMPOSTER"}'

jsonlitedb query my.db first=Paul
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{"first":"Paul","last":"McCartney","born":1942,"role":"bass"}
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb insert my.db \
    --duplicates replace \
    --json '{"first":"Paul","last":"McCartney","role":"IMPOSTER"}'

jsonlitedb query my.db first=Paul
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{"first":"Paul","last":"McCartney","role":"IMPOSTER"}
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb delete my.db || echo "Command failed, continuing"
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
Error: refusing to delete all rows without filters.
Add one or more filters (e.g. name=Paul) or use --allow-empty.
Command failed, continuing
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb delete my.db first=Paul

jsonlitedb query my.db first=Paul
```

```bash exe
jsonlitedb dump my.db
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
{"first":"John","last":"Lennon","born":1940,"role":"guitar"}
{"first":"George","last":"Harrison","born":1943,"role":"guitar"}
{"first":"Ringo","last":"Starr","born":1940,"role":"drums"}
{"first":"George","last":"Martin","born":1926,"role":"producer"}
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb dump my.db --sql
```

<!-- md-demo: result start. Do not edit; this block is overwritten. -->
```
BEGIN TRANSACTION;
CREATE TABLE items(
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT
);
INSERT INTO "items" VALUES(1,'{"first":"John","last":"Lennon","born":1940,"role":"guitar"}');
INSERT INTO "items" VALUES(3,'{"first":"George","last":"Harrison","born":1943,"role":"guitar"}');
INSERT INTO "items" VALUES(4,'{"first":"Ringo","last":"Starr","born":1940,"role":"drums"}');
INSERT INTO "items" VALUES(5,'{"first":"George","last":"Martin","born":1926,"role":"producer"}');
CREATE TABLE items_kv(
    key TEXT PRIMARY KEY,
    val TEXT
);
CREATE UNIQUE INDEX ix_items_250e4243_UNIQUE 
                ON items(
                    JSON_EXTRACT(data, '$."first"'),JSON_EXTRACT(data, '$."last"')
                );
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('items',7);
COMMIT;
```
<!-- md-demo: result end -->
```bash exe
jsonlitedb delete my.db --allow-empty
jsonlitedb dump my.db # EMPTY
```
