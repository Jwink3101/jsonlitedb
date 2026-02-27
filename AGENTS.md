# Repository Guidelines

## Project Structure & Module Organization

- `jsonlitedb/jsonlitedb.py` contains the core JSONLiteDB implementation and public API.
- The project uses a `jsonlitedb/` package directory; the version comes from `jsonlitedb.__version__` via `pyproject.toml`.
- Tests live in `tests/test_jsonlitedb.py` and `tests/test_cli.py`; `test_benchmark.py` is a benchmark script.
- `run_tests.sh` runs pytest coverage for the `tests/` directory and writes HTML output to `htmlcov/`.
- Packaging metadata is in `pyproject.toml` (no `setup.py` in this repo).
- Utility scripts include `build_help.py` and `copy_to_github.py`; notebooks live in `benchmarks.ipynb`.
- Generated artifacts and local data (e.g., `htmlcov/`, `build/`, `*.db`) should not be committed unless explicitly requested.

## Build, Test, and Development Commands

- `python -m pytest` runs the test suite.
- `./run_tests.sh` runs pytest with coverage for the `tests/` directory and generates HTML output in `htmlcov/`.
- `python -m pip install -e .` installs the project in editable mode for local development.
- `python -m jsonlitedb` runs the CLI, and the `jsonlitedb` console script is available after install.

## Development and Publishing Workflow

- Development happens in this private repo.
- Use `copy_to_github.py` to sync tracked files to the public GitHub repo before publishing.
- The sync script runs `build_help.py`, mirrors tracked files via `rsync`, and commits in the public repo.
- `readme.md` includes executed demo output injected between `<!--- BEGIN AUTO GENERATED -->` and `<!--- END AUTO GENERATED -->`; that block is overwritten on each run.
- `build_help.py` executes all tracked `.ipynb` files, but only `Demo/Basic Usage.ipynb` is inserted into the README.

## Coding Style & Naming Conventions

- Follow standard Python conventions (PEP 8) with 4-space indentation.
- Import ordering uses isort with the Black profile (`pyproject.toml` specifies `profile = "black"`).
- Code should either follow Black style or run "black ." when finished.
- Use descriptive, lowercase function names and `CapWords` for classes (`JSONLiteDB`, `QueryResult`).
- Prefer explicit keyword arguments for query helpers, e.g. `db.query(first="George", _orderby="born")`.
- For public functions and methods, prefer NumPy style docstrings.
- Markdown should have a blank new line after headings.

## Testing Guidelines

- Tests use `pytest` with coverage reporting.
- Name tests `test_*.py` and functions `test_*` (see `tests/test_jsonlitedb.py`).
- Aim to keep coverage high; the README advertises 100% coverage.
- When adding features, include both positive and failure-path tests (e.g., `pytest.raises`).

## Commit & Pull Request Guidelines

- Recent commit messages are short, sentence-case summaries (e.g., "Documentation", "tests. Still need documentation").
- Keep commits focused and describe intent rather than implementation details.
- PRs should include a clear description, test results, and any new usage examples or documentation updates.

## Security & Configuration Tips

- JSONLiteDB uses SQLite files; do not commit local `.db` files or sensitive data.
- When testing query performance or indexes, prefer temporary databases like `":memory:"`.
