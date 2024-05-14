
## releasing 1.2.2 (2024-05-14)
### Overview
This is minor patch with bug fix for parameter handling

### Changes
* fixed bug when passing default values for a `multivalued=True` parameter, values are not properly set (#219)
* updated to the latest `mmif-python` (1.0.14)


## releasing 1.2.1 (2024-04-21)
### Overview
This release includes documentation updates and bug fixes

### Additions
* lots of details were added to app metadata documentation for app developers (https://github.com/clamsproject/clams-python/issues/201)

### Changes
* fixed a bug where raw user input parameters with `multivalued=True` were not fully recorded in the output MMIF view metadata (https://github.com/clamsproject/clams-python/issues/214)


## releasing 1.2.0 (2024-04-11)
### Overview
This is a minor release that brings improved portability of `clams source` command but also breaks some backward compatibility. If your app is based on clams-python 1.0.x or 1.1.x, please read the changelog carefully. 

### Changes
- `clams source` command now work on Windows shell. The paths still, though, have to be POSIX path. We have no plan to support Windows path for `file://` URI in MMIF at the moment. 
- `ClamsApp.sign_view` method now expect the runtime parameters (dict of string to lists of values) as a second argument. Previously the second argument was optional, which is no more. CLAMS app developers who were calling this method in `_annotate()` method must directly pass down the runtime parameters from `_annotate()` argument.


## releasing 1.1.6 (2024-04-02)
### Overview
Minor release to update the `mmif-python` dependency to the latest.

### Changes
* now based on `mmif-python==1.0.13` including a hotfix for a wrong field name in MMIF serialization.


## releasing 1.1.5 (2024-04-01)
### Overview
Hot-fix to fix some compatibility issues in the app develop template 

### Changes
* reverted some changes from 3ed54b3 due to broken backward compatibility


## releasing 1.1.4 (2024-03-31)
### Overview
This release includes many changes regarding runtime parameters.

### Additions
* updated to latest mmif-python and added support for `views[].metadata.appConfiguration` field added in MMIF 1.0.4 (#166)
* initial implementation of `map` type parameters to provide (limited) support for complex data types. At the moment, `map` type parameters are expected to be parsed into string-to-string dictionary. See [the metadata jsonscheme for the full documentation](https://github.com/clamsproject/clams-python/blob/0daa2251b38f6c530d33e6902635d1445edf7bc9/clams/appmetadata/__init__.py#L159-L173) (#197)
* input and output type specifications in app metadata now can carry some additional "comments" from the developer (#200)

### Changes
* passed values to `multivalued=True` parameters has been interpreted as lists but default values weren't. Now it's fixed. (related to #197 as well, since `type=map` implies `multivalued=True`)
* input and output type properties can be (under-)specified as wildcards (#194)


## releasing 1.1.3 (2024-03-04)
### Overview
This is a minor release to catch up new version of MMIF and `mmif-python`. 

### Changes
* updated to latest mmif-python (and MMIF 1.0.2)
* small updates in API documentation regarding I/O spec in app metadata



## releasing 1.1.2 (2024-02-10)
### Overview
This release updates to the latest MMIF and `mmif-python`

### Additions
* Now based on `mmif-python` 1.0.9 and MMIF 1.0.1


## releasing 1.1.1 (2024-02-05)
### Overview
This release contains minor fixes in code and updates in documentations regarding changes in runtime parameter in the previous 1.1.0 release.

### Changes
* fixed broken links in the main repo README
* fixed outdated information regarding usage of `get_configuration` in various documentation
* fixed `properties` in I/O specification in AppMetadata are unfairly restricted to `str` values

## releasing 1.1.0 (2024-01-31)
### Overview
This is a minor-level release that fixes various bugs and adds safeguards for possible inconsistency in output MMIFs. 

### Additions
* `sign_view` now use user input parameters "as-is" whenever they are available (https://github.com/clamsproject/clams-python/issues/181)
* apps will conduct JSON validation right before it responses with MMIF output (https://github.com/clamsproject/clams-python/issues/179)
* `clams rewind` is now available to _rewind_ MMIF files (https://github.com/clamsproject/clams-python/issues/190)
``` bash 
$ clams rewind --help
usage: clams rewind [-h] [-o PATH] [-p] [-n NUMBER] [-m {app,view}] mmif_file

provides CLI to rewind a MMIF from a CLAMS pipeline.

MMIF rewinder rewinds a MMIF by deleting the last N views.
N can be specified as a number of views, or a number of producer apps.

positional arguments:
  mmif_file             Path to the input MMIF file, or '-' to read from stdin.

optional arguments:
  -h, --help            show this help message and exit
  -o PATH, --output PATH
                        Path to the rewound MMIF output file. When not given, the rewound MMIF is printed to stdout.
  -p, --pretty          Pretty-print rewound MMIF. True by default
  -n NUMBER, --number NUMBER
                        Number of views to rewind (default: interactive mode)
  -m {app,view}, --mode {app,view}
                        Number of views to rewind (default: interactive mode)
```
    

### Changes
* pre-built base container images will take less space (https://github.com/clamsproject/clams-python/issues/186)
* apps running in production mode (over gunicorn) now logs to stdout (https://github.com/clamsproject/clams-python/issues/183)
* fixed a bug in app metadata generation (https://github.com/clamsproject/clams-python/issues/187) 


## releasing 1.0.9 (2023-07-24)
### Overview
Minor release to update small issues in the app develop template. 

### Changes
* `metadata.py` from the template now includes *universal* parameters when printing out the app metadata.

## releasing 1.0.8 (2023-07-24)
### Overview
Minor release to update `mmif-python` version 

### Changes
* updated to `mmif-python==1.0.8`
* enabled a python logger for clams-apps as `self.logger`

## releasing 1.0.7 (2023-07-20)
### Overview
This release includes a bugfix and update to the latest mmif-python 

### Changes
* now based on `mmif-python==1.0.7`
* fixed some runtime parameters' default values not correctly casted (#173 )


## releasing 1.0.6 (2023-07-19)
### Overview
Minor release to update `mmif-python` version 

### Changes
* updated to `mmif-python==1.0.5`


## releasing 1.0.5 (2023-07-19)
### Overview
Minor release to update `mmif-python` version 

### Changes
* updated to `mmif-python==1.0.5`


## releasing 1.0.4 (2023-07-19)
### Overview
This release include many updates to documentation, and `clams source --scheme` flag. 

### Additions
* `--scheme` flag is added to `clams source` CLI to generate MMIF with arbitrary URI scheme for document locations (#163, also see https://github.com/clamsproject/mmif-python/pull/223) 

### Changes
* CLAMS app development documentation is updated with more details, clarification and a up-to-date tutorial (#165)
* added validation step for parameters with fixed options (#164)  


## releasing 1.0.3 (2023-06-14)
### Overview
This release include minor bug fixes. 


### Changes
* fixed #154
* fixed #155


## releasing 1.0.2 (2023-06-02)
### Overview
This release is a minor patch; see below. 

### Changes
* fixed a filename bug that prevented some files from being copied to a newly generate app template. 

## releasing 1.0.1 (2023-05-26)
### Overview
This release is about updating to `mmif-python==1.0.1`, which is based on MMIF 1.0.0. 

### Changes
* uses `mmif-python==1.0.1`
* updated some names for upcoming pedantic v2 update

## releasing 1.0.0 (2023-05-26)
### Overview
This release will be numbered as 1.0.0, but indeed it's a minor update from 0.6.3. 

### Additions
* `clams develop` now can select recipes to "install". Currently only two are supported (`app` and `gha`). Having `gha` separated enables developers of existing apps to update GHA workflows only when there's a new feature or fix in the workflows. 

``` bash 
$ clams develop --help
usage: clams develop [-h] [-r RECIPES [RECIPES ...]] -n NAME [-p [PATH]]

provides CLI to create a skeleton code for app development

Available recipes:
  - app: Skeleton code for a CLAMS app
  - gha: GtiHub Actions workflow files specific to `clamsproject` GitHub organization

optional arguments:
  -h, --help            show this help message and exit
  -r RECIPES [RECIPES ...], --recipes RECIPES [RECIPES ...]
                        Pick recipes to bake. DEFAULT: ['app', 'gha']
  -n NAME, --name NAME  The name of the directory where the baked app skeleton is placed. This name is also used to generate 1) Python class name of the app, 2) values for `name` and `identifier` fields in app-metadata, based on heuristic tokenizing and casing rules. RECOMMENDATION: only use lower case alpha-
                        numerics, do not use whitespace, use dash (`-`) character instead for word boundaries, always check for the generated names and make changes if they are incorrect. NOTE: if the name starts with `app-` or ends with `-app`, those affixes will be removed from Python class name and app
                        identifier, but will be retained in the directory name. (e.g. `app-foo-bar-app` will be converted to `FooBar` for class name, `foo-bar-app` for app identifier, and `app-foo-bar-app` for directory name.)
  -p [PATH], --parent-dir [PATH]
                        The name of the parent directory where the app skeleton directory is placed. (default: current directory)
```

### Changes
* "generic" readme file in the app template is replaced with a link to the generic user manual (soon be) published to `apps.clams.ai`. 
* now based on `mmif-python` and MMIF 1.0.0. 

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

## releasing 0.5.0 (2021-07-24)
This release contains changes in `AppMetadata` scheme and bug fix in `Restifier`.

* Non-boolean parameter values passed via query strings are now properly casted to python data types (#84)
* `url`, `dependencies` and `more` fields are added to app metadata scheme (#79, #83)
* Some app metadata fields are renamed (#80)
  * `license` -> `app_license`
  * `wrappee_version` -> `analyzer_version`
  * `wrappee_license` -> `analyzer_license`

## releasing 0.4.4 (2021-07-11)
This release includes bug fixes from mmif-python package, loosened ML library versions in docker images.



## releasing 0.4.3 (2021-06-19)
This release contains various fixes and improvements. 

* updated mmif-python to 0.4.4
* (added) C`lamsApp.get_configuration` will convert runtime parameters into actual runtime configuration that the app uses. This will help signing view.
* (fixed) Crash when `sign_view` with non-string parameter values
* (changed) MMIF with error is always prettified when returned as HTTP response
* (fixed) Adding duplicate input/output should not be allowed
* (changed) `AppMetadata.add_parameter` now has a proper signature for IDE hints


## releasing 0.4.2 (2021-06-17)
This release contains bugfixes

- fixed clams-python only worked on python==3.6
- fixed clams CLI not properly displaying help msg 
- updated latest mmif-python


## releasing 0.4.1 (2021-06-14)
This release includes minor API improvement ...

* `sign_view` now does not require runtime parameters (defaults to empty)
* `AppMetadata` class can be imported from `clams` package directly


## releasing 0.4.0 (2021-06-14)
This release includes 
* input MMIF file compatibility check (#60 )
* upgrade to mmif-python 0.4.x, which includes a lots of breaking changes. 

## releasing 0.3.0 (2021-06-04)
This new breaking release includes ... 

* definition and implementation of app metadata as JSON schema (#49, #50, #51, #52)
* adding server for production environment (based on gunicorn, #59 )
* changing HTTP code for error responses to 500 (#61 )
* and minor bugfixes 

## releasing 0.2.4 (2021-05-12)
This release includes small updates of error handling matching updates on mmif-python side. 

## releasing 0.2.3 (2021-05-01)
A new release includes

* *signing* method for an app (#48, #40)
* (premature) error stamping (#55, #36)
* smaller docker images (#54) 
* and other minor bugfixes 


## releasing 0.2.2 (2021-03-30)
* based on mmif-python 0.3.1 patch
* more documentation 
* more pre-built docker images 
* interpretation of HTTP parameters into python API arguments
* dependency for lapps/LIF

## releasing 0.2.1 (2021-03-17)
This version now based on `mmif-python` 0.3.0, which is based on MMIF spec 0.3.0. It doesn't have breaking changes, but due to the new dependency to `mmif-python` 0.3.0, it might break some apps. Please report here if it breaks your code. 

## releasing 0.2.0 (2021-02-04)
This PR contains many breaking changes, so when merged, we release as `0.2.0`.

* renamed
  * `Clams.serve` -> `Clams.app` (#35)
  * `ClamsApp::setupmetadata` -> `ClamsApp::_appmetadata` (#37)
  * `ClamsApp::annotate` -> `ClamsApp::_annotate` (#37)
* removed
  * `ClamsApp::sniff` (#37)
  * PUT requests
* changes
  * POST requests now invoke `annotate` instead of retired `sniff` method (#37)
  * prototype of parameter passing (#29, #37)
  * added HTTP response codes for errors during `annotate` (#33, #36)
  * refactored CLI components (currently only one CLI (`source`) implemented)
  * `clams source` CLI now supports custom directory prefix (#31)
  * added `ClamsApp::validate_document_files` (not supporting integrity check such as MD5 yet) (https://github.com/clamsproject/mmif/issues/150)


## releasing 0.1.3 (2020-10-09)
0.1.3 includes; 

* `clams` CLI
* `clams source` command
* replacement of `appmetadata` with `setupmetadata` in `ClamsApp` ABC 
