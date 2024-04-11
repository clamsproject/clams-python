.. _input-output: 

I/O Specification 
=================

A CLAMS app must be able to take a MMIF JSON as input as well as to return a MMIF JSON as output. MMIF is a JSON-based open source data format (with some JSON-LD components). For more details and discussions, please visit the `MMIF website <https://mmif.clams.ai>`_ and the `issue tracker <https://github.com/clamsproject/mmif/issues>`_. 

To learn more about MMIF, please visit `MMIF specification documentation <https://mmif.clams.ai/>`_.

``mmif`` package
^^^^^^^^^^^^^^^^^
``mmif-python`` PyPI package comes together with the installation of ``clams-python``, and with it, you can use ``mmif`` python package.

.. code-block:: python 

    import mmif
    from mmif.serialize import Mmif
    new_mmif = Mmif()
    # this will fail because an empty MMIF will fail to validate under the MMIF JSON schema

Because API's of the ``mmif`` package is well documented in the `mmif-python website <http://clams.ai/mmif>`_, we won't go into more details here. Please refer to the website. 

MMIF version and CLAMS apps
^^^^^^^^^^^^^^^^^^^^^^^^^^^

As some parts of ``clams-python`` implementation is relying on structure of MMIF, it is possible that a MMIF file of a specific version does not work with a CLAMS app that is based on a incompatible version of ``mmif-python``. 

As we saw in the above, when using ``Mmif`` class, the MMIF JSON string is automatically validated under the MMIF JSON schema (shipped with the ``mmif-python``).
So in most cases you don't have to worry about the compatibility issue, but it is still important to understand the versioning scheme of MMIF + ``mmif-python`` and ``clams-python``, because all ``clams-python`` distributions are depending on specific versions of ``mmif-python`` as a Python library.

.. code-block:: python

    import mmif
    mmif.__specver__

And when an app targets a specific version, it means: 

#. The app can only process input MMIF files that are valid under the jsonschema of ``mmif-python`` version.
#. The app will output MMIF files exactly versioned as the target version.

However, also take these into consideration

#. Not all MMIF updates are about the jsonschema. That means, some MMIF versions share the same schema, hence the syntactic validation process can pass for differently versioned MMIF files. 
#. Changing jsonschema is actually a *big* change in MMIF, and we will try to avoid it as much as possible. When it's unavoidable, we will release the new MMIF and ``mmif-python`` with the major version number incremented. 

For more information on the relation between ``mmif-python`` versions and MMIF specification versions, or MMIF version compatibility, please take time to read our decision on the subject `here <https://mmif.clams.ai/versioning/>`_. You can also find a table with all public ``clams-python`` packages and their target MMIF versions in the below. As we mentioned, developers don't usually need to worry about MMIF versions.

.. csv-table:: Target Specification Versions
   :file: target-versions.csv
   :header-rows: 1
