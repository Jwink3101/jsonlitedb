#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
from pathlib import Path

import jsonlitedb
from jsonlitedb import JSONLiteDB


class Stopwatch:
    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.elapsed = self.end_time - self.start_time


def benchmark(file=":memory:", N=1_000_000, **kwargs):
    if not file == ":memory:":
        Path(file).unlink(missing_ok=True)
    db = JSONLiteDB(file, kwargs)

    with db, Stopwatch() as sw:
        for ii in range(N):
            row = {
                "ii": ii,
                "ii2": ii * ii,
            }
            db.insert(row)

    print(f"INSERT {N = }: {sw.elapsed}")

    with Stopwatch() as sw:
        list(db.query(db.Q.ii == (max([0, N - 100]))))

    print(f"QUERY {N = }: {sw.elapsed}")

    with Stopwatch() as sw:
        db.create_index(db.Q.ii)

    print(f"CREATE INDEX {N = }: {sw.elapsed}")

    with Stopwatch() as sw:
        list(db.query(db.Q.ii == (max([0, N - 100]))))

    print(f"QUERY indexed {N = }: {sw.elapsed}")


if __name__ == "__main__":
    benchmark(file=":memory:", N=1_000_000)
    benchmark(file="tmp.db", N=1_000_000)
