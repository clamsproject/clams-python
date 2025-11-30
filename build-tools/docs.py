import argparse
import subprocess
import sys
import os
import shutil
from pathlib import Path

def run_command(command, cwd=None, check=True, env=None):
    """Helper to run a shell command."""
    print(f"Running: {' '.join(str(c) for c in command)}")
    result = subprocess.run(command, cwd=cwd, env=env)
    if check and result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result

def build_docs_local(source_dir: Path):
    """
    Builds documentation for the provided source directory.
    Assumes it's running in an environment with necessary tools.
    """
    print("--- Running in Local Build Mode ---")
    
    # 1. Generate source code and install in editable mode.
    print("\n--- Step 1: Installing in editable mode ---")
    try:
        run_command([sys.executable, "-m", "pip", "install", "-e", "."], cwd=source_dir)
    except SystemExit:
        print("Warning: 'pip install -e .' failed. This might be due to an externally managed environment.")
        print("Attempting to proceed with documentation build assuming dependencies are met...")

    # 2. Install documentation-specific dependencies.
    print("\n--- Step 2: Installing documentation dependencies ---")
    doc_reqs = source_dir / "build-tools" / "requirements.docs.txt"
    if not doc_reqs.exists():
        print(f"Error: Documentation requirements not found at {doc_reqs}")
        sys.exit(1)
    try:
        run_command([sys.executable, "-m", "pip", "install", "-r", str(doc_reqs)])
    except SystemExit:
        print("Warning: Failed to install documentation dependencies.")
        # Check if sphinx-build is available
        if shutil.which("sphinx-build") is None:
            print("Error: 'sphinx-build' not found and installation failed.")
            print("Please install dependencies manually or run this script inside a virtual environment.")
            sys.exit(1)
        print("Assuming dependencies are already installed...")

    # 3. Build the documentation using Sphinx.
    print("\n--- Step 3: Building Sphinx documentation ---")
    docs_source_dir = source_dir / "documentation"
    docs_build_dir = source_dir / "docs-test"
    
    # Schema generation is now handled in conf.py
    # schema_src = source_dir / "clams" / "appmetadata.jsonschema"
    # schema_dst = docs_source_dir / "appmetadata.jsonschema"
    # if schema_src.exists():
    #     shutil.copy(schema_src, schema_dst)

    sphinx_command = [
        sys.executable, "-m", "sphinx.cmd.build",
        str(docs_source_dir),
        str(docs_build_dir),
        "-b", "html",  # build html
        "-a",          # write all files (rebuild everything)
        "-E",          # don't use a saved environment, reread all files
    ]
    run_command(sphinx_command)

    print(f"\nDocumentation build complete. Output in: {docs_build_dir}")
    return docs_build_dir

def main():
    parser = argparse.ArgumentParser(
        description="Build documentation for the clams-python project."
    )
    args = parser.parse_args()
    
    build_docs_local(Path.cwd())

if __name__ == "__main__":
    main()
