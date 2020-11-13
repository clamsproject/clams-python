.. _introduction: 

Getting started
===============

Overview
--------

The CLAMS project has many moving parts to make various computational analysis tools talk to each other to create customized workflow pipelines. However the most important part of the project must be the apps published for the CLAMS platform. The CLAMS Python SDK will help app developers handling MMIF data format with high-level classes and methods in Python, and publishing their code as a CLAMS app that can be easily deployed to the site via CLAMS workflow engines, such as the `CLAMS appliance <https://appliance.clams.ai>`_.

A CLAMS app can be any software that performs automated contents analysis on text, audio, and/or image/video data stream. An app must use `MMIF <https://mmif.clams.ai>`_ as I/O format. When deployed into a CLAMS appliance, an app needs be running as a webapp wrapped in a docker container. In this documentation, we will explain what Python API's and HTTP API's an app must implement. 

Prerequisites
-------------

* `Python <https://www.python.org>`_: ``clams-python`` requires Python 3.6 or newer. We have no plan to support `Python 2.7 <https://pythonclock.org/>`_. 
* `Docker <https://www.docker.com>`_: when deployed to the CLAMS appliance, an app must be in a docker container

Installation 
------------

``clams-python`` distribution package is `available at PyPI <https://pypi.org/project/clams-python/>`_. You can use ``pip`` to install the latest version. 

.. code-block:: bash 

    pip install clams-python

Note that installing ``clams-python`` will also install ``mmif-python`` PyPI package, which is a companion python library related to the MMIF data format.

I/O Specification 
------------------

A CLAMS app must be able to take a MMIF json as input as well as to return a MMIF json as output. MMIF is a JSON(-LD)-based open source data format. For more details and discussions, please visit the `MMIF website <https://mmif.clams.ai>`_ and the `issue tracker <https://github.com/clamsproject/mmif/issues>`_. 


``mmif`` package
^^^^^^^^^^^^^^^^^
``mmif-python`` PyPI package comes together with the installation of ``clams-python``, and with it, you can use ``mmif`` python package.

.. code-block:: python 

    import mmif
    from mmif.serialize import Mmif
    new_mmif = Mmif()
    # this will fail because an empty MMIF will fail to validate against MMIF JSON schema

Because API's of the ``mmf`` package is well documented in the `mmif-python website <http://clams.ai/mmif>`_, we won't go into more details here. Please refer to the website. 

Note on versions
^^^^^^^^^^^^^^^^
``clams-python`` is under active development, so is `mmif-python`, which is a separate PyPI distribution package providing Python classes and methods to handle MMIF json string. Because of this rapid version cycles, it is often the case that a MMIF file of a certain version does not work with CLAMS SDK that is based on a different version of ``mmif-python`` from the version of the MMIF file. In every MMIF files, there must be the MMIF version encoded at the top of the file. Please keep in mind the versions you're using and be careful not to mix and match different versions. To see the MMIF specification version supported by the installed ``mmif-python`` package, look at ``mmif.__specver__`` variable.

.. code-block:: python

    import mmif
    mmif.__specver__

For more information on the relation between ``mmif-python`` versions and MMIF specification versions, please take time to read our decision on the subject `here <https://mmif.clams.ai/versioning/>`_.

CLAMS App API
-------------
A CLAMS Python app is a python class that implements and exposes three core methods; ``annotate()``, ``appmetadata()`` and ``sniff()``.  And a good place to start writing a CLAMS app is to start with inheriting :class:`clams.serve.ClamsApp`. 

* ``appmetadata()``: Returns JSON-formatted :class:`str` that contains metadata about the app. You will be implementing :meth:`clams.serve.ClamsApp.setupmetadata` instead if you're using :class:`clams.serve.ClamsApp` as a super class.
* ``sniff()``: Takes a MMIF as the only input and returns True if the app can process input MMIF.
* ``annotate()``: Takes a MMIF as the only input and processes the MMIF input, then returns serialized MMIF :class:`str`.

We provide a tutorial for writing with a real world example at <:ref:`tutorial`>. We highly recommend you to go through it. 

Note on App metadata
^^^^^^^^^^^^^^^^^^^^^
App metadata is a map where important information about the app itself is stored as key-value pairs. At the moment, there's no standard metadata scheme. In the future the app metadata will be used for automatic generation of CLAMS App index in the :ref:`appdirectory`, as well as automatic integration to Galaxy in the appliance deployment. 

HTTP webapp
-----------
To be integrated into the CLAMS appliance, a CLAMS app needs to serve as a webapp. Once your application class is ready, you can use :class:`clams.restify.Restifier` to wrap your app as a `Flask <https://palletsprojects.com/p/flask/>`_-based web application. 

.. code-block:: python 

    from clams.serve import ClamsApp
    from clams.restify import Restifier

    class AnApp(ClamsApp):
        # Implements an app that does this and that. 
        # Must implement `appmetadata`, `sniff`, `annotate` methods

    if __name__ == "__main__":
        app = AnApp()
        webapp = Restifier(app)
        webapp.run()

When running the above code, Python will start a web serve and host your CLAMS app. By default the serve will listen to ``0.0.0.0:5000``, but you can adjust hostname and port number. In this webapp, ``appmetadata``, ``sniff``, and ``annotate`` will be respectively mapped to ``GET``, ``POST`` and ``PUT`` to the root route. Hence, for example, you can ``PUT`` a MMIF file to the web app and get a response with the annotated MMIF string in the body. 

Note that with currently implementation, :class:`clams.restify.Restifier` will start the webapp in debug mode on a `Werkzeug <https://palletsprojects.com/p/werkzeug/>`_ server, which is not always suitable for a production server. For more robust and fast server, you might want to use a production-ready HTTP server. In the end of the day, for the appliance integration, all you need is a webapp the does ``appmetadata``, ``sniff``, and ``annotate`` on ``GET``, ``POST``, and ``PUT`` requests. 

Dockerization 
-------------
In addition to the HTTP service, a CLAMS app is expected to be containerized. Concretely, the appliance maker expects a CLAMS app to have a ``Dockerfile`` at the project root. Independently from being compatible with the CLAMS appliance, containerization of your app is recommended especially when your app processes video streams and dependent on complicated system-level video processing libraries (e.g. `OpenCV <https://opencv.org/>`_, `FFmpeg <https://ffmpeg.org/>`_). 

Refer to the `official documentation <https://docs.docker.com/engine/reference/builder/>`_ to learn how to write a ``Dockerfile``. To integrate to the CLAMS appliance, a dockerized CLAMS app must automatically start itself as a webapp when instantiated as a container, and listen to ``5000`` port in the container. 

We have a `public docker hub <https://hub.docker.com/orgs/clamsproject/repositories>`_, and publishing Debian-based base images to help developers write ``Dockerfile`` and save build time to install common libraries. At the moment we have a basic image with Python 3.6 and ``clams-python`` installed. We will publish more images built with commonly used video and audio processing libraries. 

CLAMS appliance integration 
----------------------------

Finally, here are requirements for an app to be appliance compatible. 

#. App code is hosted on a public git repository. 
#. App is dockerized
#. The app docker image will automatically start the app as a webapp, and listen to port 5000. 
#. ``Dockerfile`` for the dockerization is placed in the root of the git repository

To learn how to deploy your app on an appliance instance, please refer to the `appliance documentation <https://appliance.clams.ai/>`_. 

