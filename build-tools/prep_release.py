"""
Prepare release artifacts for the clams-python package.

Run while preparing a release PR, passing the version being released::

    python build-tools/prep_release.py X.Y.Z

Currently this adds a row to ``documentation/target-versions.csv`` for
the release version. The ``mmif-python`` column is read from this
package's pinned dependency in ``pyproject.toml``, and the target MMIF
spec version from the installed ``mmif.__specver__``. This script is the
single place that writes the target-versions table; the docs build only
renders it, and CI verifies (on the release PR) that a row for the PR's
version exists.

Requires an editable install (``pip install -e .``) so that
``mmif.__specver__`` is importable.
"""
import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CSV_PATH = PROJECT_ROOT / 'documentation' / 'target-versions.csv'
PYPROJECT_PATH = PROJECT_ROOT / 'pyproject.toml'

VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
TOP_ROW_RE = re.compile(r'`(\d+\.\d+\.\d+) <')
MMIF_PIN_RE = re.compile(r'mmif-python\s*==\s*(\d+\.\d+\.\d+)')


def _row(version, mmif_ver, specver):
    return (
        f'`{version} <https://pypi.org/project/clams-python/{version}/>`__,'
        f'`{mmif_ver} <https://pypi.org/project/mmif-python/{mmif_ver}/>`__,'
        f'`{specver} <https://mmif.clams.ai/{specver}/>`__'
    )


def _version_tuple(v):
    return tuple(int(x) for x in v.split('.'))


def _top_version(data_lines):
    if not data_lines:
        return None
    m = TOP_ROW_RE.match(data_lines[0])
    return m.group(1) if m else None


def _pinned_mmif_version():
    m = MMIF_PIN_RE.search(PYPROJECT_PATH.read_text())
    if not m:
        sys.exit("Error: could not find a pinned 'mmif-python==X.Y.Z' "
                 "dependency in pyproject.toml.")
    return m.group(1)


def main():
    parser = argparse.ArgumentParser(
        description="Prepare release artifacts for clams-python."
    )
    parser.add_argument(
        "version", metavar="X.Y.Z",
        help="the release version being prepared",
    )
    args = parser.parse_args()
    version = args.version

    if not VERSION_RE.match(version):
        sys.exit(f"Error: '{version}' is not a valid X.Y.Z version.")

    mmif_ver = _pinned_mmif_version()
    try:
        import mmif
        specver = mmif.__specver__
    except (ImportError, AttributeError):
        sys.exit("Error: cannot read mmif.__specver__. "
                 "Run `pip install -e .` first.")

    lines = CSV_PATH.read_text().splitlines()
    header, data = lines[0], lines[1:]
    top = _top_version(data)

    if top is not None and _version_tuple(version) < _version_tuple(top):
        sys.exit(f"Error: {version} is older than the current top row "
                 f"{top}; refusing to insert an out-of-order version.")

    new_row = _row(version, mmif_ver, specver)
    if top == version:
        data[0] = new_row            # update in place
        action = "updated"
    else:
        data.insert(0, new_row)      # prepend as the new latest
        action = "added"

    CSV_PATH.write_text('\n'.join([header] + data) + '\n')
    print(f"target-versions.csv: {action} row {version} "
          f"-> mmif-python {mmif_ver}, MMIF spec {specver}")


if __name__ == "__main__":
    main()
