
## releasing 0.6.3 (2023-05-20)
### Overview
This is a minor release

### Additions
* a new base container image with jdk8 is added 

### Changes
* protocol string used in the base url to generate app identifiers is now reverted back to `http` from `https` for consistency (all documentations of ours are using `http` in the base URL in any URI/IRI field).

## releasing 0.6.2 (2023-05-19)
### Overview
This release includes all the `clamsproject`-specific GHA workflow files in the PyPI distribution. 

### Changes
* fixed GHA workflow files were missing in the sdist uploaded to PyPI (#143)

## releasing 0.6.1 (2023-05-19)
### Overview
This release is based on a new version of `mmif-python` [0.5.2](https://github.com/clamsproject/mmif-python/blob/main/CHANGELOG.md#releasing-052-2023-05-19). Additionally, this release includes significant updates in documentation both in sphinx API documentation (website) and app starter-kit documentation, huge upgrades in GHA workflows in app-dev template, and finally small (but critical) bug fixes.

### Additions
* app directory registration GHA workflow is added to the app development template. (#134)
* documentation of `clamsproject`-specific GHA workflows included in the app-dev template.

### Changes
* now using [`mmif-python==0.5.2`](https://github.com/clamsproject/mmif-python/blob/main/CHANGELOG.md#releasing-052-2023-05-19).
* major updates in the documentation website (API doc by sphinx) to include recent changes in app metadata, I/O specs, runtime parameters, as well as `clams` CLI. (#140)
* fixed app-dev templated wasn't really included in the pypi distribution. (#132)
* fixed app version generator crashed when `git` cmd not found (in a container). (#139)
* fixed `@` sign wasn't properly serialized from `metadata.py`.


## releasing 0.6.0 (2023-05-03)
### Overview
This release contains big changes and new features, including "breaking" ones. All CLAMS apps using `clams-python==0.5.*` are recommended to update to this release. 

### Additions
* added `clams develop` CLI and made help messages for CLI more informative (#119, #116)
    * `clams develop` creates a scaffolding code for starting development of a new CLAMS app. Here's the argument structure; 
``` bash 
$ clams develop --help
usage: clams develop [-h] [-r {app}] [--no-github-actions] -n NAME [-p [PATH]]

optional arguments:
  -h, --help            show this help message and exit
  -r {app}, --recipe {app}
                        Pick a recipe to use. Currently `app` is the only option, hence there's no need to use the flag at all.
  --no-github-actions   The cookiecutter by default assumes that the app codebase will be hosted on `github.com/clamsproejct`,and add pre-shipped github actions for
                        the `clamsproject` organization setup to the skeleton codebase.Use this options to disable this behavior.
  -n NAME, --name NAME  The name of the directory where the baked app skeleton is placed. This name is also used to generate1) Python class name of the app, 2) values
                        for `name` and `identifier` fields in app-metadata, based on heuristic tokenizing and casing rules. RECOMMENDATION: only use lower case ASCII
                        alpha-numerics,do not use whitespace, use dash (`-`) character instead for word boundaries, always check for the generated names and make
                        changes if they are incorrect.
  -p [PATH], --parent-dir [PATH]
                        The name of the parent directory where the app skeleton directory is placed. (default: current directory)
```
* Prebuilt containers are now also available as arm64 images. (#126)
* In the `input` specification in app-metadata, developers can now add a list of specification. A nested list in the `input` list should be interpreted as "OR" condition. (#77)
* In the `parameters` specification in app-metadata, developers can specify if a parameter can have multiple values, using the `multivalued` key. 
    * When a parameter key is passed twice or more (with different values) in one POST request, if the parameter is multivalued, all values are aggregated into a list and passed to `_annotate` method. Otherwise, only the first value will be passed.  (#122)

### Changes
* In addition to `_appmetadata()` method, more ways for writing app-metadata are added. (#117)
    * the metadata is read from 1) `metadata.py` (recommended way), then 2) `metadata.json`, and then finally 3) `_appmetadata()` method. This change is made for future development of the app-directory.
* `app_version` value in the app-metadata is now automatically generated from local git information and developers should not manually set this value. (#114)
* `identifier` value in the app-metadata is now automatically expanded into `https://apps.clams.ai/XXX` URI format, hence developers now only need to set the `XXX` part in the app-metadata. 
* All the changes related to app-metadata are reflected in the scaffolding code template, hence developers are encouraged to update existing apps using `clams develop` command. 
* updated to use MMIF 0.5.0 and `mmif-python==0.5.1`. 
    * The big change in the MMIF 0.5.0 is the change in the CLAMS vocab type versioning scheme. And as now the responsibility of vocab type version checking is pushed down to the `mmif-python` library, `clams-python` no longer checks any version numbers in an input MMIF file. 
    * FYI, here's how vocab type versions are "checked" when comparing two `AnnotationTypes.SomeType` enum-like objects: https://github.com/clamsproject/mmif-python/blob/88040395b7349f49058a9bf315628bed426e3d51/templates/python/vocabulary/base_types.txt#L152-L166

## releasing 0.5.3 (2023-03-20)
### Overview
This release includes update to the latest MMIF / `mmif-python`, and big improvements on handling runtime parameters.

### Additions
* undefined parameters now trigger warnings, not errors, utilizing new `warnings` field in [MMIF 0.4.2](https://mmif.clams.ai/0.4.2/) (#101 , #106)

### Changes
* removed usages of deprecated "freezing" behavior of MMIF objects (#109)
* fixed bugs around setting default values for `bool` type runtime parameters (#111)


## releasing 0.5.2 (2023-02-02)
This release contains updates of the python version (#102) and "uncapping" of python dependencies (#89), and a small update in handling `pretty` (and future "universal") parameter (#99). 

## releasing 0.5.1 (2022-03-25)
This release contains fixes in the development pipelines (#97 ) and dependency ( #95). 
