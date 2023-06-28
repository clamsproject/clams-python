.. _introduction: 

Getting started
===============

Overview
--------

The CLAMS project has many moving parts to make various computational analysis tools talk to each other to create customized workflows. However the most important part of the project must be the apps published for the CLAMS platform. The CLAMS Python SDK will help app developers handling MMIF data format with high-level classes and methods in Python, and publishing their code as a CLAMS app that can be easily deployed to the site via CLAMS workflow engines, such as the `CLAMS appliance <https://appliance.clams.ai>`_.

A CLAMS app can be any software that performs automated contents analysis on text, audio, and/or image/video data stream, while using `MMIF <https://mmif.clams.ai>`_ as I/O format. When deployed into a CLAMS workflow engine, an app needs be running as a webapp wrapped in a container. In this documentation, we will explain what Python API's and HTTP API's an app must implement. 


Prerequisites
-------------

* `Python <https://www.python.org>`_: the latest ``clams-python`` requires Python 3.8 or newer. We have no plan to support `Python 2.7 <https://pythonclock.org/>`_. 
* Containerization software: when deployed to a CLAMS workflow engine, an app must be containerized. Developers can choose any containerization software for doing so, but ``clams-python`` SDK is developed with `Docker <https://www.docker.com>`_ in mind.

Installation 
------------

``clams-python`` distribution package is `available at PyPI <https://pypi.org/project/clams-python/>`_. You can use ``pip`` to install the latest version. 

.. code-block:: bash 

    pip install clams-python

Note that installing ``clams-python`` will also install ``mmif-python`` PyPI package, which is a companion python library related to the MMIF data format. More information regarding MMIF specifications can be found `here <https://mmif.clams.ai/>`_. Documentation on ``mmif-python`` is available at the `Python API documentation website <https://clams.ai/mmif-python>`_.

Quick Start with the App Template
---------------------------------

``clams-python`` comes with a cookiecutter template for creating a CLAMS app. You can use it to create a new app project.

.. code-block:: bash 

    clams develop --help

The newly created project will have a ``README.md`` file that explains how to develop and deploy the app. Here we will explain the basic structure of the project. Developing a CLAMS app has three (or four depending on the underlying analyzer) major components. 

#. (Writing computational analysis code, or use existing code in Python)
#. Make the analyzer to speak MMIF by wrapping with :class:`clams.app.ClamsApp`. 
#. Make the app into a web app by wrapping with :class:`clams.restify.Restifier`. 
#. Containerize the app by writing a ``Containerfile`` or ``Dockerfile``.

CLAMS App API
^^^^^^^^^^^^^
A CLAMS Python app is a python class that implements and exposes two core methods: ``annotate()``, ``appmetadata()``. In essence, these methods (discussed further below) are wrappers around ``_annotate()`` and ``_appmetadata()``, and they provide some common functionality such as making sure the output is serialized into a string.

* :meth:`~clams.app.ClamsApp.annotate`: Takes a MMIF as input and processes the MMIF input, then returns serialized MMIF :class:`str`.
* :meth:`~clams.app.ClamsApp.appmetadata`: Returns JSON-formatted :class:`str` that contains metadata about the app. 

A good place to start writing a CLAMS app is to start with inheriting :class:`clams.app.ClamsApp`. Let's talk about the two methods in detail when inheriting the class.

annotate()
""""""""""

The ``annotate()`` method is the core method of a CLAMS app. It takes a MMIF JSON string as the main input, along with other `kwargs <https://docs.python.org/3.8/glossary.html#term-argument>`_ for runtime configurations, and analyzes the MMIF input, then returns analysis results in a serialized MMIF :class:`str`. 
When you inherit :class:`~clams.app.ClamsApp`, you need to implement 

* :meth:`~clams.app.ClamsApp._annotate` instead of :meth:`~clams.app.ClamsApp.annotate` (read the docstrings as they contain important information about the app implementation).

For a text processing app, ``_annotate()`` is mostly concerned with finding text documents, creating new views and calling the code that runs over the text and inserts the results.

As a developer you can expose different behaviors of the ``annotate()`` method by providing configurable parameters as keyword arguments of the method. For example, you can have the user specify a re-sample rate of an audio file to be analyzed by providing a ``resample_rate`` parameter. 

.. note::
  These runtime configurations are not part of the MMIF input, but for reproducible analysis, you should record these configurations in the output MMIF. 

.. note::
  There are *universal* parameters defined at the SDK-level that all CLAMS apps commonly use. See :const:`clams.app.ClamsApp.universal_parameters`. 

.. warning::
  All the runtime configurations should be pre-announced in the app metadata.

appmetadata()
"""""""""""""

App metadata is a map where important information about the app itself is stored as key-value pairs. That said, the ``appmetadata()`` method should not perform any analysis on the input MMIF. In fact, it shouldn't take any input at all. 

When using :class:`clams.app.ClamsApp`, you have different options to implement information source for the metadata. See :meth:`~clams.app.ClamsApp._load_appmetadata` for the options, and <:ref:`appmetadata`> for the metadata specification. 

.. note::

  In the future, the app metadata will be used for automatic generation of :ref:`appdirectory`.

HTTP webapp
^^^^^^^^^^^
To be integrated into the CLAMS appliance, a CLAMS app needs to serve as a webapp. Once your application class is ready, you can use :class:`clams.restify.Restifier` to wrap your app as a `Flask <https://palletsprojects.com/p/flask/>`_-based web application. 

.. code-block:: python 

    from clams.app import ClamsApp
    from clams.restify import Restifier

    class AnApp(ClamsApp):
        # Implements an app that does this and that. 

    if __name__ == "__main__":
        app = AnApp()
        webapp = Restifier(app)
        webapp.run()

When running the above code, Python will start a web server and host your CLAMS app. By default the serve will listen to ``0.0.0.0:5000``, but you can adjust hostname and port number. In this webapp, ``appmetadata`` and ``annotate`` will be respectively mapped to ``GET``, and ``POST`` to the root route. Hence, for example, you can ``POST`` a MMIF file to the web app and get a response with the annotated MMIF string in the body.

.. note::
  Now with HTTP interface, users can pass runtime configuration as `URL query strings <https://en.wikipedia.org/wiki/Query_string>`_. As the values of query string parameters are always strings, ``Restifier`` will try to convert the values to the types specified in the app metadata, using :class:`clams.restify.ParameterCaster`. 

In the above example, :meth:`clams.restify.Restifier.run` will start the webapp in debug mode on a `Werkzeug <https://palletsprojects.com/p/werkzeug/>`_ server, which is not always suitable for a production server. For a more robust server that can handle multiple requests asynchronously, you might want to use a production-ready HTTP server. In such a case you can use :meth:`~clams.restify.Restifier.serve_production`, which will spin up a multi-worker `Gunicorn <https://docs.gunicorn.org>`_ server. If you don't like it (because, for example, gunicorn does not support Windows OS), you can write your own HTTP wrapper. In the end of the day, all you need is a webapp that maps ``appmetadata`` and ``annotate`` on ``GET`` and ``POST`` requests.

Containerization 
^^^^^^^^^^^^^^^^
In addition to the HTTP service, a CLAMS app is expected to be containerized for seamless deployment to CLAMS workflow engines. Also, independently from being compatible with the CLAMS platform, containerization of your app is recommended especially when your app processes video streams and is dependent on complicated system-level video processing libraries (e.g. `OpenCV <https://opencv.org/>`_, `FFmpeg <https://ffmpeg.org/>`_). 

When you start developing an app with ``clams develop`` command, the command will create a ``Containerfile`` with some instructions as inline comments for you (you can always start from scratch with any containerization tool you like). 

.. note::
  If you are part of CLAMS team and you want to publish your app to the ``https://github.com/clamsproject`` organization, ``clams develop`` command will also create a GitHub actions files to automatically build and push an app image to the organization's container registry. For the actions to work, you must use the name ``Containerfile`` instead of ``Dockerfile``.

If you are not familiar with ``Containerfile`` or ``Dockerfile``, refer to the `official documentation <https://docs.docker.com/engine/reference/builder/>`_ to learn how to write one. To integrate to the CLAMS workflow engines, a containerized CLAMS app must automatically start itself as a webapp when instantiated as a container, and listen to ``5000`` port.

We have a `public GitHub Container Repository <https://github.com/orgs/clamsproject/packages>`_, and publishing Debian-based base images to help developers write ``Containerfile`` and save build time to install common libraries. At the moment we have a basic image with Python 3.6 and ``clams-python`` installed. We will publish more images built with commonly used video and audio processing libraries. 

