"""
Publish the clams-python package.

This script is equivalent to `make publish` in the old Makefile build:
    1. Generate CHANGELOG.md from merged release PRs (requires `gh` CLI)
    2. Upload dist/ to PyPI via twine (requires TWINE_PASSWORD env var)

Credentials are passed via environment variables (twine reads them
natively):
    TWINE_USERNAME  — defaults to __token__ for API tokens
    TWINE_PASSWORD  — the PyPI/TestPyPI API token
    TWINE_REPOSITORY_URL — override for TestPyPI (or use --testpypi)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
TESTPYPI_URL = "https://test.pypi.org/legacy/"


def run_command(command, cwd=None, capture=False, check=False):
    """Helper to run a shell command."""
    print(f"Running: {' '.join(str(c) for c in command)}")
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=capture,
        text=capture,
    )
    if check and result.returncode != 0:
        print(
            f"Error: Command failed with exit code "
            f"{result.returncode}"
        )
        sys.exit(result.returncode)
    return result


def check_gh_available():
    """Check if gh CLI is installed and authenticated."""
    result = run_command(
        ["gh", "auth", "status"],
        capture=True,
    )
    return result.returncode == 0


def generate_changelog(repo=None):
    """
    Generate CHANGELOG.md from merged release PRs.

    :param repo: GitHub repo in owner/name format.
        If None, uses the repo from the current git remote.
    """
    project_root = SCRIPT_DIR.parent

    repo_args = ["--repo", repo] if repo else []

    # Query merged PRs with "releas" in title
    result = run_command(
        ["gh", "pr", "list",
         "-L", "1000",
         "-s", "merged",
         "--json", "number,title,body,mergedAt"]
        + repo_args,
        cwd=project_root,
        capture=True,
    )
    if result.returncode != 0:
        print(f"Error querying PRs: {result.stderr}")
        return False

    prs = json.loads(result.stdout)
    # Filter to release PRs
    release_prs = [
        pr for pr in prs
        if pr["title"].lower().startswith("releas")
    ]

    if not release_prs:
        print("No release PRs found.")
        return False

    # Sort by merge date (newest first)
    release_prs.sort(
        key=lambda pr: pr["mergedAt"], reverse=True
    )

    # Format changelog
    lines = []
    for pr in release_prs:
        merged_date = pr["mergedAt"][:10]  # YYYY-MM-DD
        lines.append(f"\n## {pr['title']} ({merged_date})")
        if pr["body"]:
            lines.append(pr["body"])
        lines.append("")

    changelog_path = project_root / "CHANGELOG.md"
    changelog_path.write_text("\n".join(lines))
    print(
        f"CHANGELOG.md written with {len(release_prs)} entries."
    )
    return True


def upload_to_pypi(testpypi=False):
    """
    Upload dist/ to PyPI via twine.

    Auth via env vars: TWINE_USERNAME (default: __token__),
    TWINE_PASSWORD (required).
    """
    project_root = SCRIPT_DIR.parent
    dist_dir = project_root / "dist"

    tarballs = list(dist_dir.glob("*.tar.gz"))
    if not tarballs:
        print("No tarball found in dist/. Run build.py first.")
        sys.exit(1)

    if not os.environ.get("TWINE_PASSWORD"):
        print(
            "Warning: TWINE_PASSWORD not set. "
            "Skipping PyPI upload."
        )
        print(
            "Set TWINE_PASSWORD to your PyPI API token "
            "to enable upload."
        )
        return

    # Set default username for token auth
    if not os.environ.get("TWINE_USERNAME"):
        os.environ["TWINE_USERNAME"] = "__token__"

    # Install twine
    run_command(
        [sys.executable, "-m", "pip", "install", "twine"],
        cwd=project_root,
    )

    # Build upload command
    cmd = [sys.executable, "-m", "twine", "upload"]
    if testpypi:
        cmd.extend(["--repository-url", TESTPYPI_URL])
    cmd.extend(str(t) for t in tarballs)

    run_command(cmd, cwd=project_root, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Publish: generate CHANGELOG and upload to PyPI."
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repo in owner/name format "
             "(default: infer from git remote)."
    )
    parser.add_argument(
        "--skip-changelog",
        action="store_true",
        help="Skip changelog generation."
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip PyPI upload (changelog only)."
    )
    parser.add_argument(
        "--testpypi",
        action="store_true",
        help="Upload to TestPyPI instead of PyPI."
    )
    args = parser.parse_args()

    # Changelog
    if args.skip_changelog:
        print("Skipping changelog generation.")
    elif not check_gh_available():
        print(
            "Warning: gh CLI not available or not authenticated. "
            "Skipping changelog generation."
        )
    else:
        if not generate_changelog(repo=args.repo):
            sys.exit(1)

    # Upload
    if args.skip_upload:
        print("Skipping PyPI upload.")
    else:
        upload_to_pypi(testpypi=args.testpypi)


if __name__ == "__main__":
    main()
