.. _appmetadata: 

CLAMS App Metadata
##################

Overview
********

Every CLAMS app must provide information about the app itself. We call this set of information **App Metadata**. 

Format
======

A CLAMS App Metadata should be able to be serialized into a JSON string. 

Input/Output type specification
===============================

Essentially, all CLAMS apps are designed to take one MMIF file as input and produce another MMIF file as output. In this 
section, we will discuss how to specify the *semantics* of the input and output MMIF files in the App Metadata, and how 
that information should be formatted in terms of the App Metadata syntax, concretely by using ``input`` and ``output`` 
lists and type vocabularies where ``@type`` are defined.


.. note::
   CLAMS App Metadata is encoded in JSON format, but is not part of MMIF specification.
   Full json schema for app metadata is available in the below section.
   When an app is published to the CLAMS app directory, the app metadata will be rendered as a HTML page, with some 
   additional information about submission. Visit the `CLAMS app directory <https://apps.clams.ai>`_ to see how the app 
   metadata is rendered.

TODO: write-up on the "best" practice for writing ``input`` and ``output`` sections in the app metadata, making (re-)use
of prose from mmif.clams.ai documentation, and CLAMS and MMIF vocabularies.


Annotation types in MMIF
------------------------

As described in the `MMIF documentation <https://mmif.clams.ai>`_, MMIF files can contain annotations of various types. 
Currently, CLAMS team is using the following vocabularies with pre-defined annotation types: 

- `CLAMS vocabulary <https://mmif.clams.ai/|specver|/vocabulary>`_
http://vocab.lappsgrid.org
_ LAPPS types
type properties 


Metadata Schema
===============

The schema for app metadata is as follows. 
(You can also download the schema in `JSON Schema <https://json-schema.org/>`_ format from `here <appmetadata.jsonschema>`_.)

.. jsonschema:: appmetadata.jsonschema 
   :lift_description: True
   :lift_title: True
   :lift_definitions: True


