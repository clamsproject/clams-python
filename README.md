# CLAMS sdk for python 

**NOTE** that this project is in pre-alpha stage and being actively developed. Nothing is guaranteed to reliably work for the moment and developers need to be very careful when using APIs implemented here. Please use [the issue track](https://github.com/clamsproject/clams-python/issues) to report bugs and malfunctions, or send us pull requests for even more contribution. 

## CLAMS project
[CLAMS project](https://clams.ai) aims at free and open-source software platform for computational analysis and metadata generation applications for multimedia material. To achieve interoperability between various computational applications developed be different vendors, which is absolutely necessary for piping applications together supported by user-friendly workflow engines, we are also developing JSON(-LD)-based MultiMedia Interchange Format ([MMIF](https://mmif.clams.ai))

## clams-python
`clams-python` is a Python implementation of the CLAMS SDK. `clams-python` supports; 

1. handling MMIF files for input and output specification for CLAMS apps
1. a base class to start developing a CLAMS app
1. a flask-based wrapper to run a Python CLAMS app as a HTTP web app

## For more ...
For user manuals and Python API documentation, take a look at [the SDK website](https://clams.ai/clams-python).

For MMIF-specific Python API documentation, take a look at the [mmif-python website](https://clams.ai/mmif-python).
