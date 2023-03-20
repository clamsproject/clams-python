
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
