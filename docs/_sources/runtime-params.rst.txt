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
