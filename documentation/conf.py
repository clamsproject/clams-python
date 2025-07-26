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
from pathlib import Path
import shutil
import sys

import mmif

proj_root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root_dir))


# -- Project information -----------------------------------------------------

project = proj_root_dir.name
copyright = f'{datetime.date.today().year}, Brandeis LLC'
author = 'Brandeis LLC'
version = open(proj_root_dir / 'VERSION').read().strip()
root_doc = 'index'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
        'sphinx.ext.autodoc',
        'sphinx.ext.linkcode',
        'sphinx.ext.intersphinx',
        'sphinx_rtd_theme',
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


# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
#  html_static_path = ['_static']

# hide document source view link at the top 
html_show_sourcelink = False


# function used by `linkcode` extension
def linkcode_resolve(domain, info):
    if domain != 'py':
        return None
    if not info['module']:
        return None
    filename = info['module'].replace('.', '/')
    return f"https://github.com/clamsproject/clams-python/tree/main/{filename}/__init__.py"


def update_target_spec():
    target_vers_csv = Path(__file__).parent / 'target-versions.csv'
    with open("../VERSION", 'r') as version_f:
        version = version_f.read().strip()
    mmifver = mmif.__version__
    specver = mmif.__specver__
    with open(target_vers_csv) as in_f, open(f'{target_vers_csv}.new', 'w') as out_f:
        lines = in_f.readlines()
        if not lines[1].startswith(f"`{version}"):
            lines.insert(1, f"`{version} <https://pypi.org/project/clams-python/{version}/>`__,`{mmifver} <https://pypi.org/project/mmif-python/{mmifver}/>`__,`{specver} <https://mmif.clams.ai/{specver}/>`__\n")
        for line in lines:
            out_f.write(line)
        shutil.move(out_f.name, in_f.name)

update_target_spec()
