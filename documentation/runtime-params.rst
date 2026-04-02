.. _runtime-params:

Runtime Configuration
=====================

As Python API
-------------

Using keyword arguments in the :meth:`~clams.app.ClamsApp.annotate` method, you 
can make your app configurable at the runtime. 

For example, an app can be configured to use a different combination of optional 
input annotation types, or to use a different unit for the output time-based 
annotations. See an example below.

.. code-block:: python

  class NamedEntityRecognizerApp(ClamsApp):
      def __init__(self)
          super().__init__()
          self.ner_model = self._load_model()

      def annotate(self, input_mmif, **parameters)
          ...  # preamble to "sign" the view and prepare a new view to use
          labels_to_use = parameters.get('labels', ['PERSON', 'ORG', 'GPE'])
          text = self.get_text(input_mmif)
          ne = self.ner_model(text)
          for ent in ne:
              if ent.label_ in labels_to_use:
                  self.add_annotation(input_mmif, ent.start_char, ent.end_char, ent.label_)
          return input_mmif 
          
      ...

When you use a configuration parameter in your app, you should also expose it 
to the user via the app metadata. See :ref:`appmetadata` section for more details.

As HTTP Server
--------------

When running as a HTTP server, a CLAMS app should be stateless (or always set to 
default states), and all the state should be "configured" by the client for each 
request, via the runtime configuration parameters we described above if necessary.
For HTTP interface, users can enter configuration values via 
`query strings <https://en.wikipedia.org/wiki/Query_string>`_ as part of the 
request URL. For example, if the user wants to use the above app as a server 
with the `labels` parameter only set to ``PERSON`` and ``ORG``, then the user 
can send a ``POST`` request to the server with the following URL:

.. code-block:: bash

  http://app-server:5000?labels=PERSON&labels=ORG

Note that for this example to work, the parameter must be specified as
``multivalued=True`` in the app metadata, so that the SDK can collect multiple
values for the same parameter name in a single python list and pass to the
``annotate()`` method. Otherwise, only the *first* value will be passed.

.. _runtime-params-detailed:

Parameter Types
---------------

Each runtime parameter has a ``type`` that determines how user-provided string
values are cast into Python objects before reaching your ``_annotate()`` method.
The supported types are: ``string``, ``integer``, ``number``, ``boolean``, and
``map``.

Primitive types
^^^^^^^^^^^^^^^

``string``
  Values are passed through as-is (no casting).

  .. code-block:: python

    metadata.add_parameter(name='outputFormat', type='string',
                           default='json',
                           description='Output format.')

``integer``
  Values are cast to Python ``int`` via ``int(value)``.

  .. code-block:: python

    metadata.add_parameter(name='minFrameCount', type='integer',
                           default=5,
                           description='Minimum number of frames.')

``number``
  Values are cast to Python ``float`` via ``float(value)``.

  .. code-block:: python

    metadata.add_parameter(name='threshold', type='number',
                           default=0.5,
                           description='Confidence threshold.')

``boolean``
  Values are cast to Python ``bool``. The following string values are
  recognized as ``False``: ``False``, ``false``, ``F``, ``f``, ``0``.
  Everything else is treated as ``True``. Boolean parameters always have
  ``multivalued=False`` (enforced by the SDK).

  .. code-block:: python

    metadata.add_parameter(name='pretty', type='boolean',
                           default=False,
                           description='Pretty-print JSON output.')

Multivalued parameters
^^^^^^^^^^^^^^^^^^^^^^

When a parameter can accept more than one value, set ``multivalued=True``.
The SDK will always pass a **list** to ``_annotate()``, even when the user
provides only a single value.

.. code-block:: python

  metadata.add_parameter(name='labels', type='string',
                         multivalued=True,
                         default=['PERSON', 'ORG'],
                         description='Annotation labels to use.')

To pass multiple values:

- via query string: repeat the parameter name

  .. code-block:: bash

    http://app-server:5000?labels=PERSON&labels=ORG

- via CLI: list values after the flag

  .. code-block:: bash

    python cli.py --labels PERSON ORG

.. note::

  ``boolean`` parameters always force ``multivalued=False``.

Map type parameters
^^^^^^^^^^^^^^^^^^^

Map parameters allow users to pass key-value pairs that arrive in
``_annotate()`` as a Python ``dict``. Declaring ``type='map'`` automatically
forces ``multivalued=True``.

.. code-block:: python

  metadata.add_parameter(name='labelMap', type='map',
                         default=['B:bars', 'S:slate'],
                         description='Mapping from source to target labels.')

Each value uses a colon (``:``) as the key-value delimiter::

  KEY:VALUE

**Colons are not allowed in keys.** The first colon in the string is always used
as the delimiter. If colons appear in the value portion (after the first colon),
the SDK will emit a warning. When the same key is passed more than once, the
last value wins.

To pass map values:

- via query string: repeat the parameter name with each ``KEY:VALUE`` pair

  .. code-block:: bash

    http://app-server:5000?labelMap=B:bars&labelMap=S:slate

- via CLI: list pairs after the flag

  .. code-block:: bash

    python cli.py --labelMap B:bars S:slate

Inside ``_annotate()``, the parameter arrives as::

  {'B': 'bars', 'S': 'slate'}

Default values must be a list of colon-separated strings::

  default=['key1:value1', 'key2:value2']

For more complex value structures (e.g., comma-separated lists within values),
the app developer is responsible for further parsing and should document the
expected format in the parameter's ``description`` field.
