#! /usr/bin/env python3
import distutils.cmd
import os
from os import path
import shutil

import setuptools

name = "clams-python"
cmdclass = {}

try:
    from sphinx.setup_command import BuildDoc

    cmdclass['build_sphinx'] = BuildDoc
except ImportError:
    print('WARNING: sphinx not available, not building docs')

with open("VERSION", 'r') as version_f:
    version = version_f.read().strip()

with open('README.md') as readme:
    long_desc = readme.read()

with open('requirements.txt') as requirements:
    requires = requirements.readlines()

ver_pack_dir = path.join('clams', 'ver')
shutil.rmtree(ver_pack_dir, ignore_errors=True)
os.makedirs(ver_pack_dir, exist_ok=True)
init_mod = open(path.join(ver_pack_dir, '__init__.py'), 'w')
init_mod.write(f'__version__ = "{version}"')
init_mod.close()


class DoNothing(distutils.cmd.Command):
    description = "run base code until `setuptools.setup()` line and exits 0."
    user_options = []

    def initialize_options(self) -> None:
        pass

    def finalize_options(self) -> None:
        pass

    def run(self):
        pass


cmdclass['donothing'] = DoNothing

setuptools.setup(
    name="clams-python",
    version=version,
    author="Brandeis Lab for Linguistics and Computation",
    author_email="admin@clams.ai",
    description="A collection of APIs to develop CLAMS app for python",
    long_description=long_desc,
    long_description_content_type="text/markdown",
    url="https://clams.ai",
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Framework :: Flask',
        'Framework :: Pytest',
        'Intended Audience :: Developers ',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3 :: Only',
    ],
    cmdclass=cmdclass,
    command_options={
        'build_sphinx': {
            'source_dir': ('setup.py', 'documentation'),
            'project': ('setup.py', name),
            'version': ('setup.py', version),
            #  'release': ('setup.py', release),
            'build_dir': ('setup.py', 'documentation/_build'),
            'builder': ('setup.py', 'html'),
        }
    },
    install_requires=requires,
    python_requires='>=3.6',
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': [
            'clams = clams.__init__:cli',
        ],
    },
)
