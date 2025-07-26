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
section, we will discuss how to specify, in the App Metadata, the *semantics* of the input and output MMIF files, and 
how that information should be formatted in terms of the App Metadata syntax, concretely by using ``input`` and 
``output`` lists and type vocabularies where ``@type`` are defined.


.. note::
   CLAMS App Metadata is encoded in JSON format, but is not part of MMIF specification.
   Full json schema for app metadata is available in the below section.
   When an app is published to the CLAMS app directory, the app metadata will be rendered as a HTML page, with some 
   additional information about submission. Visit the `CLAMS app directory <https://apps.clams.ai>`_ to see how the app 
   metadata is rendered.

Annotation types in MMIF
------------------------

As described in the `MMIF documentation <https://mmif.clams.ai>`_, MMIF files can contain annotations of various types. 
Currently, CLAMS team is using the following vocabularies with pre-defined annotation types: 

- `CLAMS vocabulary <https://mmif.clams.ai/|specver|/vocabulary>`_
- `LAPPS types <http://vocab.lappsgrid.org>`_

Each annotation object type in the vocabularies has a unique URI that is used as the value of the ``@type`` field.
However, more important part of the type definition in the context of CLAMS app development is the ``metadata`` and
``properties`` fields. These fields provide additional information about the annotation type. Semantically, there is 
no differences between a metadata field and a property field. The difference is in the intended use of the field. 
a ``metadata`` field is used to provide common information about a group of annotation objects of the same type, while 
a ``properties`` field is used to provide information about the individual annotation instance. In practice, metadata 
fields are placed in the view metadata (``view[].metatadata.contains``) and properties fields are placed in the 
annotation object itself. Because of this lack of distinction in the semantics, we will use the term "type property" to 
refer to both metadata and properties in the context of annotation type (I/O) specifications in the app metadata. 

Type definitions in the vocabularies are intentionally kept minimal and underspecified. This is because the definitions
are meant to be extended by an app developers. For example, the LAPPS vocabulary defines a type called ``Token``,
primarily to represent a token in a natural language text. However, the usage of the type can be extended to represent
a sub-word token used in a machine learning model, or a minimal unit of a sign language video. If the app developer
needs to add additional information to the type definition, they can do so by adding arbitrary properties to the type
definition in action. In such a case, the app developer is expected to provide the explanation of the extended type in
the app metadata. See below for the syntax of I/O specification in the app metadata. 

Syntax for I/O specification in App Metadata
--------------------------------------------

In the App Metadata, the input and output types are specified as lists of objects. Each object in the list should have
the following fields:

- ``@type``: The URI of the annotation type. This field is required.
- ``description``: A human-readable description of the annotation type. This field is optional.
- ``properties``: A key-value pairs of type properties. This field is optional.
- ``required``: A boolean value indicating whether the annotation type is required as input. This field is optional and 
  defaults to ``true``. Not applicable for output types.


Simple case - using types as defined in the vocabularies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the simplest case, where a developer merely re-uses an annotation type definition and pre-defined properties, an 
input specification can be as simple as the following:

.. code-block:: python

    { 
      # other app metadata fields, 
      "input": 
      [
        {
          "@type": "http://vocab.lappsgrid.org/Token", 
          "properties": {
            "posTagSet": "https://www.ling.upenn.edu/courses/Fall_2003/ling001/penn_treebank_pos.html"
          }
        }
      ],
      # and more app metadata fields, 
    }
    
In the above example, the developer is declaring the app is expecting ``Token`` annotation objects, with a ``posTagSet`` 
property of which value is the URL of the Penn Treebank POS tag set, *verbatim*, in the input MMIF, and all other 
existing annotation types in the input MMIF will be ignored during processing. There are some *grammar* of how this 
``input`` list can be written. 

- The value of a property specification can be a verbatim string, or ``"*"`` to indicate that the property can have 
  any value. 
- If the app expects multiple types of annotations, the ``input`` field should contain multiple objects in the list. 
- And if the app expects "one-of" specified types, one can specify the set of those types in a nested list. One nested 
  list in the input specification means one *required* type. 
- And finally, if an input type is optional (i.e., ``required=false``), it indicates that the app can use extra 
  information from the optional annotations. In such a case, it is recommended to provide a description of differences 
  in the output MMIF when the extra information is available.

For example, here is a more complex example of the simple case:

.. code-block:: python

    { 
      # other app metadata fields, 
      "input": 
      [
        [
          { "@type": "https://mmif.clams.ai/vocabulary/AudioDocument/v1/" },
          { "@type": "https://mmif.clams.ai/vocabulary/VideoDocument/v1/" }
        ],
        {
          "@type": "https://mmif.clams.ai/vocabulary/TimeFrame/v5", 
          "properties": {
            "label": "speech",
          }
          "required": false
        }, 
      ],
      # and more app metadata fields, 
    }

This app is a speech-to-text (automatic speech recognition) app that can take either an audio document or a video
document and transcribe the speech in the document. The app can also take a ``TimeFrame`` annotation objects with 
``label="speech"`` property. When speech time frames are available, app can perform transcription only on the speech
segments, to save time and compute power. 

Another example with even more complex input specification:

.. code-block:: python

    { 
      # other app metadata fields, 
      "input": 
      [
        { "@type": "https://mmif.clams.ai/vocabulary/VideoDocument/v1/" },
        [
          {
            "@type": "https://mmif.clams.ai/vocabulary/TimeFrame/v5", 
            "properties": {
              "timeUnit": "*"
              "label": "slate",
            }
          }, 
          {
            "@type": "https://mmif.clams.ai/vocabulary/TimeFrame/v5", 
            "properties": {
              "timeUnit": "*"
              "label": "chyron",
            }
          }
        ]
      ],
      # and more app metadata fields, 
    }

This is a text recognition app that can take a video document **and** ``TimeFrame`` annotations that are labels as 
either ``slate`` or ``chyron``, and have ``timeUnit`` properties. The value of the ``timeUnit`` property doesn't matter, 
but the input time frames must have it. 

.. note::
   Unfortunately, currently there is no way to specify optional properties within the type definition.

Finally, let's take a look at the ``output`` specification of a scene recognition CLAMS app:

.. code-block:: python

    { 
      # other app metadata fields, 
      "output": 
      [
          {
            "@type": "https://mmif.clams.ai/vocabulary/TimePoint/v4/", 
            "description": "An individual \"still frame\"-level image classification results.",
            "properties": {
                "timeUnit": "milliseconds",
                "labelset": ["slate", "chyron", "talking-heads-no-text"],
                "classification": "*",
                "label": "*"
            }
          }
      ],
      # and more app metadata fields, 
    }

Note that in the actual output MMIF, more properties can be stored in the ``TimePoint`` objects. The output 
specification in the app metadata is a subset of the properties to be produced that are useful for type checking
in the downstream apps, as well as for human readers to understand the output.

Extended case - adding custom properties to the type definition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the type definition is extended on the fly, developers are expected to provide the extended specification in the 
form of key-value pairs in the ``properties`` field. The grammar of the JSON object does not change, but developers are
expected to provide a verbose description of the type extension in the ``description`` field. 

Runtime parameter specification
===============================

CLAMS apps designed to be run as HTTP servers, preferably as `stateless <https://en.wikipedia.org/wiki/Stateless_protocol>`_.
When accepting HTTP requests, the app should take the request data payload (body) as the input MMIF, and any exposed 
configurations should be read from query strings in the URL. 

That said, the only allowed data type for users to pass as parameter values at the request time is a string. Hence, the 
app developer is responsible for parsing the string values into the appropriate data types. (``clams-python`` SDK 
provides some basic parsing functions, automatically called by the web framework wrapper.) At the app metadata level, 
developers can specify the expected parameter data types, among ``integer``, ``number``, ``string``, ``boolean``, 
``map``, and also can specify the default value of the parameter (when specified, default values should be properly 
*typed*, not as strings). Noticeably, there's NO ``list`` in the available data types, and that is because a parameter 
can be specified as ``multivalued=True`` to accept multiple values as a list. For details of how SDK's built-in 
parameter value parsing works, please refer to the App Metadata json scheme (in the `below <#clams-app-runtime-parameter>`_ 
section). 

Syntax for parameter specification in App Metadata
--------------------------------------------------

Metadata Schema
===============

The schema for app metadata is as follows. 
(You can also download the schema in `JSON Schema <https://json-schema.org/>`_ format from `here <appmetadata.jsonschema>`_.)

.. jsonschema:: appmetadata.jsonschema 
   :lift_description: True
   :lift_title: True
   :lift_definitions: True


