# CLAMS SDK for Python and guidelines for app developers

## Overview

A CLAMS app can be any software that performs automated contents analysis on text, audio, and/or image/video data stream. An app uses MMIF as I/O format and when deployed into a CLAMS instance, an app needs be running as a webapp and integrated with the Galaxy workflow engine that will call specific HTTP requests to the root (`/`) of the webapp URL. 

### I/O requirements 
A CLAMS app must use [Multi-Media Interchange Format (MMIF)](https://mmif.clams.ai) for input and output data format. 

### HTTP requirements
A CLAMS app must serve as a webapp that supports three HTTP API's. 

* `GET` at `/`
  * When requested, the app needs to response with its metadata. 
* `POST` at `/` with MMIF annotation as payload
  * When requested, the app needs to *sniff* the payload and figure out whether and what analysis it can perform with the data. 
* `PUT` at `/` with MMIF annotation as payload
  * When requested, the app needs to perform analysis on the passed data and response a MMIF annotation with an additional `view`.

## Python SDK 

### Requirements and Installation 
CLAMS Python SDK is under active development. The SDK is written for Python 3 and might not work with Python 2. We have no plan to fully support [Python 2](https://pythonclock.org/). The SDK package can be installed directly from the source code repository using pip. 
```
pip install git+https://github.com/clamsproject/clams-python-sdk.git
```

### API's

Currently the SDK provides Python API's for 

1. MMIF serialization/deserialization.
1. Making the app a webapp with required HTTP API's (using [Flask framework](http://flask.pocoo.org/)). 

### MMIF serialization 

Use classes in `clams.serialize` package. `clams.Mmif`, `clams.Annotation`, and `clams.View` will be main classes for read in and write out MMIF JSON-LD data. `clams.vocab` package provides static strings for linked-data definitions. 

### CLAMS App

When using the SDK to build a app for CLAMS instance, an app must inherit `clams.ClamsApp` abstract class and implement three methods

1. `appmetadata`: returns string of app metadata. An app metadata is a JSON-LD string that contains information about the app - name, vendor, functionality, etc. CLAMS app metadata is part of MMIF and more details can be found in [MMIF documentation](https://mmif.clams.ai). Will be mapped to `GET` HTTP API. 
1. `sniff`: return True if input MMIF data can be handled by the app. Will be mapped to `POST` HTTP API. 
1. `annotate`: analyze the input data in MMIF format and return a MMIF annotation with an additional view with added analysis. Will be mapped to `PUT` HTTP API. 

### CLAMS Webapp

To be integrated with the workflow engine (Galaxy), an app needs to serve as a webapp. This is supported in the SDK via `clams.restify.Restifier` class. Thus the main entry point python script should initiate the app, wrap it in a flask web app, and finally start the flask app. Here's an example: 

``` python
from clams.serve import ClamsApp
from clams.restify import Restifier

class AnApp(ClamsApp):
    # Implements an app that does this and that. 
    # Must implement `appmetadata`, `sniff`, `annotate` methods

if __name__ == "__main__":
    app = AnApp()
    webapp = Restifier(app)
    webapp.run()
```


<!-- Global site tag (gtag.js) - Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=UA-141649660-3"></script>

<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'UA-141649660-3');
</script>


