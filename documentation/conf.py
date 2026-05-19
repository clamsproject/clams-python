# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

import datetime
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import mmif

proj_root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root_dir))


# -- Project information -----------------------------------------------------

project = proj_root_dir.name
blob_base_url = f'https://github.com/clamsproject/{project}/blob'
copyright = f'{datetime.date.today().year}, Brandeis LLC'
author = 'Brandeis LLC'
try:
    from importlib.metadata import version as _get_version
    version = _get_version('clams-python')
except Exception:
    print("WARNING: could not read package version, using 'dev'.")
    version = 'dev'
root_doc = 'index'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
        'sphinx.ext.autodoc',
        'sphinx.ext.linkcode',
        'sphinx.ext.intersphinx',
        'sphinx-jsonschema',
        'm2r2'
]
#  autodoc_typehints = 'description'
source_suffix = [".rst", ".md"]

# mapping for external documentations
intersphinx_mapping = {
        'python': ('https://docs.python.org/3', None),
        'mmif': (f'https://clamsproject.github.io/mmif-python/{mmif.__version__}', None)
        }


templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
# dynamically generated files
exclude_patterns.extend(['cli_help.rst', 'whatsnew.md'])
# this is user manual, and not part of API docs, will be used in a remote site
exclude_patterns.extend(['clamsapp.md'])


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'furo'
html_extra_path = ['appmetadata.jsonschema']
html_static_path = []  # No static path for now, can be created if needed
html_show_sourcelink = True  # Furo handles this well, no need to hide

# Theme options for visual consistency with CLAMS branding
html_theme_options = {
    # "light_logo": "logo.png", # TODO: Add logo files if available
    # "dark_logo": "logo.png",
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "source_repository": "https://github.com/clamsproject/clams-python",
    "source_branch": "main", # Default branch for "Edit on GitHub" links
    "source_directory": "documentation/",

    # CLAMS brand colors
    "light_css_variables": {
        "color-brand-primary": "#008AFF",
        "color-brand-content": "#0085A1",
        "color-link": "#008AFF",
        "color-link-hover": "#0085A1",
    },
    # Dark mode variables can be added here if needed
}


# function used by `linkcode` extension
def linkcode_resolve(domain, info):
    if domain != 'py' or not info.get('module'):
        return None

    try:
        # Find the Python object
        obj = sys.modules.get(info['module'])
        if obj is None: return None
        for part in info['fullname'].split('.'):
            obj = getattr(obj, part)

        # Get the source file and line numbers
        # Use inspect.unwrap to handle decorated objects
        unwrapped_obj = inspect.unwrap(obj)
        filename = inspect.getsourcefile(unwrapped_obj)
        if not filename: return None

        lines, start_lineno = inspect.getsourcelines(unwrapped_obj)
        end_lineno = start_lineno + len(lines) - 1

        # clams-python docs are single-version, always pointing to main
        git_ref = 'main'

        # Get file path relative to repository root
        repo_root = Path(__file__).parent.parent
        rel_path = Path(filename).relative_to(repo_root)

        return f"{blob_base_url}/{git_ref}/{rel_path}#L{start_lineno}-L{end_lineno}"

    except Exception:
        # Don't fail the entire build if one link fails, just return None
        return None


def generate_whatsnew_rst(app):
    """
    Generate whatsnew.md by fetching the latest release PR body
    from GitHub via ``gh pr list``.

    Falls back gracefully if ``gh`` is unavailable (local builds).
    """
    output_path = (proj_root_dir / 'documentation'
                   / 'whatsnew.md')
    repo = f'clamsproject/{project}'

    try:
        result = subprocess.run(
            ['gh', 'pr', 'list',
             '-s', 'merged', '-B', 'main',
             '-L', '100',
             '--json', 'title,body',
             '--repo', repo],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        prs = json.loads(result.stdout)
        pr = next(
            (p for p in prs
             if p['title'].startswith('releasing ')),
            None,
        )
        if pr is None:
            raise RuntimeError("No release PR found")
        title = pr['title']
        body = pr.get('body', '')

        with open(output_path, 'w') as f:
            f.write(f"## {title}\n\n")
            f.write(f"(Full changelog: "
                    f"[CHANGELOG.md]"
                    f"({blob_base_url}/main/CHANGELOG.md))\n\n")
            if body:
                f.write(body)

    except Exception as e:
        with open(output_path, 'w') as f:
            f.write("")


def generate_jsonschema(app):
    import json
    from clams.appmetadata import AppMetadata

    # Generate schema using Pydantic v2 API
    schema_dict = AppMetadata.model_json_schema()
    
    output_path = Path(app.srcdir) / 'appmetadata.jsonschema'
    with open(output_path, 'w') as f:
        json.dump(schema_dict, f, indent=2)


def update_target_spec(app):
    target_vers_csv = Path(__file__).parent / 'target-versions.csv'
    version = _get_version('clams-python')
    # Skip dev/dummy versions to avoid dirtying the git-tracked CSV
    if 'dev' in version or not re.match(r'^\d+\.\d+\.\d+$', version):
        return
    mmifver = mmif.__version__
    specver = mmif.__specver__
    with open(target_vers_csv) as in_f, open(f'{target_vers_csv}.new', 'w') as out_f:
        lines = in_f.readlines()
        if not lines[1].startswith(f"`{version}"):
            lines.insert(1, f"`{version} <https://pypi.org/project/clams-python/{version}/>`__,`{mmifver} <https://pypi.org/project/mmif-python/{mmifver}/>`__,`{specver} <https://mmif.clams.ai/{specver}/>`__\n")
        for line in lines:
            out_f.write(line)
        shutil.move(out_f.name, in_f.name)


def setup(app):
    app.connect('builder-inited', generate_whatsnew_rst)
    app.connect('builder-inited', generate_jsonschema)
    app.connect('builder-inited', update_target_spec)
