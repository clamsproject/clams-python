"""
Build documentation for the clams-python project.

This script is equivalent to:
    1. pip install -e .[docs]
    2. sphinx-build -b html -a -E documentation <output-dir>
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(command, cwd=None, check=True):
    """Helper to run a shell command."""
    print(f"Running: {' '.join(str(c) for c in command)}")
    result = subprocess.run(command, cwd=cwd)
    if check and result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result


def build_docs_local(source_dir: Path, output_dir: Path):
    """
    Builds documentation for the provided source directory.

    :param source_dir: Path to the source directory containing the project.
    :param output_dir: Path to the output directory for built documentation.
    """
    print("--- Building clams-python documentation ---")

    # Install package with docs dependencies in editable mode.
    print("\n--- Step 1: Installing package with docs dependencies ---")
    try:
        run_command(
            [sys.executable, "-m", "pip", "install", "-e", ".[docs]"],
            cwd=source_dir,
        )
    except SystemExit:
        print("Warning: 'pip install -e .[docs]' failed.")
        if shutil.which("sphinx-build") is None:
            print("Error: 'sphinx-build' not found and installation failed.")
            sys.exit(1)
        print("Assuming dependencies are already installed...")

    # Build the documentation using Sphinx.
    print("\n--- Step 2: Building Sphinx documentation ---")
    docs_source_dir = source_dir / "documentation"

    sphinx_command = [
        sys.executable, "-m", "sphinx.cmd.build",
        str(docs_source_dir),
        str(output_dir),
        "-b", "html",  # build html
        "-a",          # write all files (rebuild everything)
        "-E",          # don't use a saved environment, reread all files
    ]
    run_command(sphinx_command)

    print(f"\nDocumentation build complete. Output in: {output_dir}")
    return output_dir


def main():
    parser = argparse.ArgumentParser(
        description="Build documentation for the clams-python project."
    )
    parser.add_argument(
        "--build-ver",
        metavar="<version>",
        default=None,
        help="Accepted for CLI compatibility with other SDK repos. "
             "Ignored by this script (clams-python uses "
             "unversioned documentation)."
    )
    parser.add_argument(
        "--output-dir",
        metavar="<path>",
        default="docs-test",
        help="The directory for documentation output "
             "(default: docs-test)."
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    build_docs_local(Path.cwd(), output_dir)


if __name__ == "__main__":
    main()
