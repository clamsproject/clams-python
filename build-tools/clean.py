"""
Clean build artifacts, caches, and generated files.

Replaces ``make clean`` / ``make distclean`` from the old Makefile.
"""
import argparse
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Directories to remove
CLEAN_DIRS = [
    "build", "dist", "*.egg-info", "clams_python-*",
    ".pytest_cache", ".pytype", ".hypothesis",
    "tests/.hypothesis", "htmlcov",
    "docs-test",
]

# Files to remove
CLEAN_FILES = [
    "coverage.xml", ".coverage",
]

# Glob patterns for recursive removal
CLEAN_GLOBS = [
    "**/__pycache__",
]


def clean(root: Path):
    removed = []

    for pattern in CLEAN_DIRS:
        for p in root.glob(pattern):
            if p.is_dir():
                shutil.rmtree(p)
                removed.append(str(p.relative_to(root)))

    for name in CLEAN_FILES:
        p = root / name
        if p.exists():
            p.unlink()
            removed.append(str(p.relative_to(root)))

    for pattern in CLEAN_GLOBS:
        for p in root.glob(pattern):
            if p.is_dir():
                shutil.rmtree(p)
                removed.append(str(p.relative_to(root)))

    if removed:
        print(f"Removed {len(removed)} items:")
        for item in sorted(removed):
            print(f"  {item}")
    else:
        print("Nothing to clean.")


def main():
    parser = argparse.ArgumentParser(
        description="Clean build artifacts and caches."
    )
    parser.parse_args()
    clean(PROJECT_ROOT)


if __name__ == "__main__":
    main()
