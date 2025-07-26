#! /usr/bin/env python3
import os
from os import path
import shutil

name = "clams-python"
cmdclass = {}

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

import setuptools

setuptools.setup(
    name=name,
    version=version,
    author="Brandeis Lab for Linguistics and Computation",
    author_email="admin@clams.ai",
    description="A collection of APIs to develop CLAMS app for python",
    long_description=long_desc,
    long_description_content_type="text/markdown",
    url="https://clams.ai",
    license="Apache-2.0",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Framework :: Flask',
        'Framework :: Pytest',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3 :: Only',
    ],
    cmdclass=cmdclass,
    # this is for *building*, building (build, bdist_*) doesn't get along with MANIFEST.in
    # so using this param explicitly is much safer implementation
    package_data={
        'clams': ['develop/templates/**/*', 'develop/templates/**/.*']
    },
    install_requires=requires,
    python_requires='>=3.10',
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': [
            'clams = clams.__init__:cli',
        ],
    },
)
