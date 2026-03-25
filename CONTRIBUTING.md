# Contributing to clams-python

## Prerequisites

- Python 3.10+
- `gh` CLI (for changelog generation)

## Setup

```bash
pip install -e ".[dev]"
```

Unlike the old `setup.py`-based workflow, an editable install
(`pip install -e .`) is now required before running tests or building
docs. The package uses `importlib.metadata` for version resolution at
runtime, which only works when the package is registered in the
environment. You can no longer run `pytest` or `pytype` directly
against the source tree without installing first. If you want to avoid
pulling in all dependencies, `pip install -e . --no-deps` is sufficient
to register the package metadata.

## Local Development

All build tasks are handled by scripts in `build-tools/`. Each script
is self-contained and installs its own dependencies as needed.

| Task | Command |
|------|---------|
| Build (sdist + wheel) | `python build-tools/build.py` |
| Run tests | `python build-tools/test.py` |
| Build docs | `python build-tools/docs.py` |
| Clean artifacts | `python build-tools/clean.py` |
| Publish | `python build-tools/publish.py` |

All scripts support `--help` for full usage details.

### Build

```bash
python build-tools/build.py
```

Produces sdist and wheel in `dist/`.

### Test

```bash
python build-tools/test.py
```

Runs pytest with coverage. Use `--skip-install` if you already have the
package installed in editable mode.

### Documentation

```bash
python build-tools/docs.py
```

Builds Sphinx HTML docs into `docs-test/` (override with `--output-dir`).
The `--build-ver` flag is accepted for CI compatibility but has no effect
— clams-python uses unversioned documentation.

### Versioning

Versions are derived automatically from git tags via `setuptools-scm`.
There is no `VERSION` file to manage. At runtime, the version is
accessed through `importlib.metadata`:

```python
from clams.ver import __version__
```

For a dev install without a matching tag, `setuptools-scm` generates a
version like `1.4.1.dev20+gaf551a4e4.d20260325`.

## Migration from Makefile

The old `Makefile` and `setup.py` have been removed. If you are
accustomed to the old workflow, here is a mapping:

| Old command | New equivalent |
|-------------|----------------|
| `make package` / `python setup.py sdist` | `python build-tools/build.py` |
| `make develop` / `python setup.py develop` | `pip install -e ".[dev]"` |
| `make test` | `python build-tools/test.py` |
| `make doc` | `python build-tools/docs.py` |
| `make version` / `make devversion` | Automatic via `setuptools-scm` (tag-based) |
| `make clean` | `python build-tools/clean.py` |
| `make publish` | `python build-tools/publish.py` |
