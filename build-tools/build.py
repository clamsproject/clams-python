"""
Build the clams-python package.

Installs dependencies and runs `python -m build` to produce sdist + wheel.
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
        description="Build the clams-python package."
    )
    parser.parse_args()

    project_root = SCRIPT_DIR.parent

    # Install dev + build dependencies
    print("--- Installing dependencies ---")
    run_command(
        [sys.executable, "-m", "pip",
         "install", "-e", ".[dev]", "build"],
        cwd=project_root,
    )

    # Build sdist + wheel
    print("\n--- Building sdist + wheel ---")
    run_command(
        [sys.executable, "-m", "build"],
        cwd=project_root,
    )

    print("\nBuild complete. Output in: dist/")


if __name__ == "__main__":
    main()
