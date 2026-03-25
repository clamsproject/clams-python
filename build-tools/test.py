"""
Run tests for the clams-python package.

This script is equivalent to ``make test`` in the Makefile-based repos:
    pip install -e ".[test]"
    pytype --config .pytype.cfg clams
    python -m pytest --cov=clams --cov-report=xml
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def run_command(command, cwd=None, check=True):
    """Helper to run a shell command."""
    print(f"Running: {' '.join(str(c) for c in command)}")
    result = subprocess.run(command, cwd=cwd)
    if check and result.returncode != 0:
        print(
            f"Error: Command failed with exit code "
            f"{result.returncode}"
        )
        sys.exit(result.returncode)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run tests for the clams-python package."
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip pip install step "
             "(useful if already installed)."
    )
    args = parser.parse_args()

    project_root = SCRIPT_DIR.parent

    # Install package with test dependencies
    if not args.skip_install:
        print("--- Installing package with test dependencies ---")
        run_command(
            [sys.executable, "-m", "pip",
             "install", "-e", ".[test]"],
            cwd=project_root,
        )

    # Run pytype static analysis
    print("\n--- Running pytype ---")
    run_command(
        ["pytype", "--config", ".pytype.cfg", "clams"],
        cwd=project_root,
    )

    # Run pytest with coverage
    print("\n--- Running pytest ---")
    run_command(
        [sys.executable, "-m", "pytest",
         "--cov=clams", "--cov-report=xml"],
        cwd=project_root,
    )

    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
