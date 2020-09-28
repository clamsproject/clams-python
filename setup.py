import setuptools

with open("VERSION", 'r') as version_f: 
    version = version_f.read().strip()

with open('README.md') as readme:
    long_desc = readme.read()

with open('requirements.txt') as requirements:
    requires = requirements.readlines()

setuptools.setup(
    name="clams-python", 
    version=version,
    author="Brandeis Lab for Linguistics and Computation", 
    author_email="admin@clams.al",
    description="A collection of APIs to develop CLAMS app for python", 
    long_description=long_desc,
    long_description_content_type="text/markdown",
    url="https://www.clams.ai",
    classifiers=[
    'Development Status :: 2 - Pre-Alpha',
    'Framework :: Flask',
    'Framework :: Pytest',
    'Intended Audience :: Developers ',
    'License :: OSI Approved :: Apache Software License',
    'Programming Language :: Python :: 3 :: Only',
    ],
    install_requires=requires,
    python_requires='>=3.6',
    packages=setuptools.find_packages() 
)
