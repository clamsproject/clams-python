.. _header-n0:

Tutorial: writing a CLAMS app
=============================

A short demonstration of how to wrap an existing processing tool as a
CLAMS application

.. _header-n3:

The Example: Kaldi
------------------

-  We wrapped the Kaldi ASR tool

-  More specifically, we wrapped the Kaldi + Pop Up Archive docker image
   from HiPSTAS

-  This tool takes in audio files, performs automatic speech
   recognition, and generates transcripts consisting of tokens aligned
   with timecodes

-  The code in this tutorial is from
   https://github.com/clamsproject/app-puakaldi-wrapper. Click through
   to see the code in full, and check out our other apps in the
   clamsproject organization for more examples.

.. _header-n13:

A sample Kaldi transcript
-------------------------

.. code:: javascript

   {
     "words": [
       {
         "word": "ah",
         "time": 0.07,
         "duration": "2.59"
       },
       {
         "word": "oh",
         "time": 2.66,
         "duration": "5.93"
       },
       {
         "word": "yeah",
         "time": 8.59,
         "duration": "0.67"
       }
     ]
   }

.. _header-n15:

...translated into a MMIF view
------------------------------

First, the front matter:

.. code:: javascript

   {
     "id": "v_0",
     "metadata": {
       "app": "http://mmif.clams.ai/apps/kaldi/0.1.0",
       "contains": {
         "http://mmif.clams.ai/0.2.1/vocabulary/TextDocument": {},
         "http://vocab.lappsgrid.org/Token": {},
         "http://mmif.clams.ai/0.2.1/vocabulary/TimeFrame": {
           "unit": "milliseconds",
           "document": "d1"
         },
         "http://mmif.clams.ai/0.2.1/vocabulary/Alignment": {}
       }
     },
   ...

Then, the first two annotations:

.. code:: javascript

   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/TextDocument",
     "properties": {
       "text": {
         "@value": "ah oh yeah"
       },
       "id": "td1"
     }
   },
   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/Alignment",
     "properties": {
       "source": "d1",
       "target": "td1",
       "id": "a1"
     }
   },

Then, three annotations for each word:

.. code:: javascript

   {
     "@type": "http://vocab.lappsgrid.org/Token",
     "properties": {
       "word": "ah",
       "start": 0,
       "end": 2,
       "document": "v_0:td1",
       "id": "t1"
     }
   },
   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/TimeFrame",
     "properties": {
       "frameType": "speech",
       "start": 70,
       "end": 2660,
       "id": "tf1"
     }
   },
   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/Alignment",
     "properties": {
       "source": "tf1",
       "target": "t1",
       "id": "a2"
     }
   },
   {
     "@type": "http://vocab.lappsgrid.org/Token",
     "properties": {
       "word": "oh",
       "start": 3,
       "end": 5,
       "document": "v_0:td1",
       "id": "t2"
     }
   },
   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/TimeFrame",
     "properties": {
       "frameType": "speech",
       "start": 2660,
       "end": 8590,
       "id": "tf2"
     }
   },
   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/Alignment",
     "properties": {
       "source": "tf2",
       "target": "t2",
       "id": "a3"
     }
   },
   {
     "@type": "http://vocab.lappsgrid.org/Token",
     "properties": {
       "word": "yeah",
       "start": 6,
       "end": 10,
       "document": "v_0:td1",
       "id": "t3"
     }
   },
   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/TimeFrame",
     "properties": {
       "frameType": "speech",
       "start": 8590,
       "end": 9260,
       "id": "tf3"
     }
   },
   {
     "@type": "http://mmif.clams.ai/0.2.1/vocabulary/Alignment",
     "properties": {
       "source": "tf3",
       "target": "t3",
       "id": "a4"
     }
   }

.. _header-n22:

So, how do we generate this?
----------------------------

Three steps:

1. Setting up a CLAMS app in Python

2. Figuring out how to wrangle the data

3. Making a Docker container

.. _header-n31:

1. Setting up a CLAMS app in Python
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each CLAMS app should be a subclass of the ``ClamsApp`` class in the
clams-python package.

Things to do:

1. Write a ``setupmetadata`` method

2. Write a ``sniff`` method

3. Write an ``annotate`` method

4. Set up a Flask app

Steps 1 and 2 are still a bit unconstrained at this point.

.. _header-n44:

1.1 ``setupmetadata``
^^^^^^^^^^^^^^^^^^^^^

This method should just return a dictionary containing the metadata
relevant to your app. Metadata format will be standardized at a later
date but for now is rather informal

.. code:: python

   class Kaldi(ClamsApp):

       def setupmetadata(self) -> dict:
           return {
               "name": "Kaldi Wrapper",
               "description": "This tool wraps the Kaldi ASR tool",
               "vendor": "Team CLAMS",
               "iri": f"http://mmif.clams.ai/apps/kaldi/{APP_VERSION}",
               "wrappee": WRAPPED_IMAGE,
               "requires": [DocumentTypes.AudioDocument.value],
               "produces": [
                   DocumentTypes.TextDocument.value,
                   AnnotationTypes.TimeFrame.value,
                   AnnotationTypes.Alignment.value,
                   Uri.TOKEN
               ]
           }

.. _header-n47:

1.2 ``sniff(mmif)``
^^^^^^^^^^^^^^^^^^^

This method should return a Boolean value signifying whether the
passed-in MMIF data would be accepted by the app. For Kaldi, this means
the MMIF file should contain at least one AudioDocument pointing to a
location:

.. code:: python

   def sniff(self, mmif) -> bool:
       if type(mmif) is not Mmif:
           mmif = Mmif(mmif)
       return len(mmif.get_documents_locations(DocumentTypes.AudioDocument.value)) > 0

.. _header-n50:

1.3 ``annotate(mmif)``
^^^^^^^^^^^^^^^^^^^^^^

This method should accept a MMIF file as its parameter. You will see
that in the Kaldi wrapper’s method signature, there are additional
parameters; these are filled in later by this wrapper’s CLI.

This is where the bulk of your logic will go.

Let's walk through the highlights of the ``annotate`` method for the
Kaldi app.

The first step is to deserialize the MMIF data so that we can use the
``mmif-python`` API:

.. code:: python

   def annotate(self, mmif: Union[str, dict, Mmif], run_kaldi=True, pretty=False) -> str:
       mmif_obj: Mmif
       if isinstance(mmif, Mmif):
           mmif_obj: Mmif = mmif
       else:
           mmif_obj: Mmif = Mmif(mmif)

We then retrieve the ``AudioDocument``\ s that we want and collect their
locations into a list.

Note that if we only needed the list of locations, we could have used
``Mmif.get_documents_locations(at_type)``.

.. code:: python

   # get AudioDocuments with locations
   docs = [document for document in mmif_obj.documents
           if document.at_type == DocumentTypes.AudioDocument.value 
           and len(document.location) > 0]

   files = [document.location for document in docs]

We then pass these file locations to a subroutine that prepares the
audio files for Kaldi with ffmpeg and runs Kaldi using ``subprocess``,
storing Kaldi’s generated JSON transcripts in a temporary directory
using the ``tempfile`` Python module:

.. code:: python

   def kaldi(files: list) -> tempfile.TemporaryDirectory:
       # make a temporary dir for kaldi-ready audio files
       audio_tmpdir = tempfile.TemporaryDirectory()
       # make another temporary dir to store resulting .json files
       trans_tmpdir = tempfile.TemporaryDirectory()

       for audio_name in files: 
           audio_basename = os.path.splitext(os.path.basename(audio_name))[0]
           subprocess.run(['ffmpeg', '-i', audio_name, '-ac', '1', '-ar', '16000',
                            f'{audio_tmpdir.name}/{audio_basename}_16kHz.wav'])
           subprocess.run([
               f'{KALDI_EXPERIMENT_DIR}/run.sh', 
               f'{audio_tmpdir.name}/{audio_basename}_16kHz.wav', 
               f'{trans_tmpdir.name}/{audio_basename}.json'
               ])
       audio_tmpdir.cleanup()
       return trans_tmpdir

And now the fun SDK stuff!

First up is the high-level logic.

For each generated transcript, we create a new view in the MMIF file and
add the appropriate metadata:

.. code:: python

   for basename, transcript in json_transcripts.items():
       # convert transcript to MMIF view
       view: View = mmif_obj.new_view()
       self.stamp_view(view, docs_dict[basename].id)

Next, we generate the entire transcript for the TextDocument and
character index information for the tokens:

.. code:: python

       # index and join tokens
       indices, doc = self.index_and_join_tokens([token['word'] for token in transcript['words']])

Then we create and add the TextDocument and its alignment to the source
AudioDocument:

.. code:: python

       # make annotations
       td = self.create_td(doc, 0)
       view.add_document(td)
       align_1 = self.create_align(docs_dict[basename], td, 0)
       view.add_annotation(align_1)

Finally, we iterate through the tokens in the transcript and create the
triplets of time frames, tokens, and alignments for each token:

.. code:: python

       for index, word_obj in enumerate(transcript['words']):
           tf = self.create_tf(word_obj['time'], word_obj['duration'], index)
           token = self.create_token(word_obj['word'], index, indices, f'{view.id}:{td.id}')
           align = self.create_align(tf, token, index+1)  # one more alignment than the others
           view.add_annotation(token)
           view.add_annotation(tf)
           view.add_annotation(align)

Next, let's take a look at how we're generating the view metadata and
creating the different annotations.

First, the metadata:

.. code:: python

   def stamp_view(self, view: View, tf_source_id: str) -> None:
       if view.is_frozen():
           raise ValueError("can't modify an old view")
       view.metadata['app'] = self.metadata['iri']
       view.new_contain(DocumentTypes.TextDocument.value)
       view.new_contain(Uri.TOKEN)
       view.new_contain(AnnotationTypes.TimeFrame.value, {'unit': 'milliseconds', 'document': tf_source_id})
       view.new_contain(AnnotationTypes.Alignment.value)

We use the ``DocumentTypes`` and AnnotationTypes enums from
``mmif-python`` and the ``Uri`` enum from ``lapps`` to add the URIs for
the different types of annotation this view contains as well as any
metadata for each type in the view.

Next, the text document:

.. code:: python

   @staticmethod
   def create_td(doc: str, index: int) -> Document:
       text = Text()
       text.value = doc
       td = Document()
       td.id = TEXT_DOCUMENT_PREFIX + str(index + 1)
       td.at_type = DocumentTypes.TextDocument.value
       td.properties.text = text
       return td

Here, we create the ``TextDocument`` for the entire transcript using the
``mmif-python`` API, creating a ``Text`` object to contain the
transcript and populating the ``Document`` object with that and the
``id`` and ``@type`` information.

The token:

.. code:: python

   @staticmethod
   def create_token(word: str, index: int, indices: List[Tuple[int, int]], source_doc_id: str) -> Annotation:
       token = Annotation()
       token.at_type = Uri.TOKEN
       token.id = TOKEN_PREFIX + str(index + 1)
       token.add_property('word', word)
       token.add_property('start', indices[index][0])
       token.add_property('end', indices[index][1])
       token.add_property('document', source_doc_id)
       return token

Here, we create the ``Token`` using the ``mmif-python`` API, filling out
the desired properties with the character position information we
generated before and the source document ID of those indices.

The time frame:

.. code:: python

   @staticmethod
   def create_tf(time: float, duration: str, index: int) -> Annotation:
       tf = Annotation()
       tf.at_type = AnnotationTypes.TimeFrame.value
       tf.id = TIME_FRAME_PREFIX + str(index + 1)
       tf.properties['frameType'] = 'speech'
       # times should be in milliseconds
       tf.properties['start'] = int(time * 1000)
       tf.properties['end'] = int((time + float(duration)) * 1000)
       return tf

Here, we create the ``TimeFrame`` using the ``mmif-python`` API, filling
out the desired properties and calculating the start and end times in
milliseconds from the JSON data, which is in start/duration form.

The alignment:

.. code:: python

   @staticmethod
   def create_align(source: Annotation, target: Annotation, index: int) -> Annotation:
       align = Annotation()
       align.at_type = AnnotationTypes.Alignment.value
       align.id = ALIGNMENT_PREFIX + str(index + 1)
       align.properties['source'] = source.id
       align.properties['target'] = target.id
       return align

Here, we create the ``Alignment`` between the ``TimeFrame`` and the
``Token`` using the ``mmif-python`` API, filling out the appropriate
properties by using the ``id`` property of an ``Annotation`` object.

.. _header-n87:

1.4 Flask app
^^^^^^^^^^^^^

We use the CLAMS RESTful API:

.. code:: python

   kaldi_app = Kaldi()
   annotate = kaldi_app.annotate
   kaldi_app.annotate = lambda *args, **kwargs: annotate(*args,
                                                         run_kaldi=parsed_args.no_kaldi,
                                                         pretty=parsed_args.pretty)
   kaldi_service = Restifier(kaldi_app)
   kaldi_service.run()

We use partial application to configure the RESTified application with
the keyword arguments we saw for the ``annotate`` method.

-  ``functools.partial`` would probably have been more Pythonic here

For this app, I wrote a command line interface with argparse to allow
running Kaldi once on demand instead of as a Flask server, and to adjust
those keyword arguments for either run method.

Your ``if __name__ == '__main__'`` section can be as short as this,
though:

.. code:: python

   kaldi_app = Kaldi()
   kaldi_service = Restifier(kaldi_app)
   kaldi_service.run()

Well, I suppose if we're being technical, it could be as short as this:

.. code:: python

   Restifier(Kaldi()).run()

.. _header-n99:

2. Wrangling data
~~~~~~~~~~~~~~~~~

We have to turn MMIF into usable data for our tool to process, then turn
the output of that tool back into MMIF.

In the walkthrough of the ``annotate`` method, we saw both of these
steps.

.. _header-n102:

2.1 MMIF to tool
^^^^^^^^^^^^^^^^

This Kaldi app operates on external files that the MMIF file points to,
so all we needed to do was extract AudioDocuments from the MMIF
documents list and locate their audio files.

For other apps, this might involve extracting all the Token annotations
from each view in the MMIF file, or finding a view with speech and
non-speech segmentations and using them to chop up an audio file to
process only the speech segments (there’s a Segmented Kaldi app that
does just that!).

The type of wrangling you have to do here will vary wildly from app to
app, and can be less involved (as here) or much more involved.

.. _header-n106:

2.2 Tool to MMIF
^^^^^^^^^^^^^^^^

Kaldi generated JSON transcripts for us; we wanted to extract all the
tokens from these transcripts and create several types of annotations in
a new view.

Running ``annotate`` will always create at least one new view with at
least one annotation in it.

Deciding how you want to structure your data is part creativity and part
research—you should think about how you want your app to interoperate
with other apps. If there’s an existing app that outputs the same kind
of data as yours will, you might model your app’s output off of that
app’s output.

.. _header-n110:

3. Making a Docker container
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CLAMS apps will generally run as Flask servers in Docker containers.

Writing a Dockerfile for your CLAMS app will likely be pretty simple. We
have an image on Docker Hub that you can extend:
https://hub.docker.com/r/clamsproject/clams-python.

For the Kaldi wrapper, we instead extended HiPSTAS’ own Docker image,
which has Kaldi and the Pop Up Archive model preinstalled.

Here's the ``Dockerfile`` for the Kaldi app:

.. code:: dockerfile

   FROM hipstas/kaldi-pop-up-archive:v1

   LABEL maintainer="Angus L'Herrou <piraka@brandeis.edu>"

   # hipstas/kaldi-pop-up-archive:v1 uses Ubuntu 16.10 Yakkety, which is dead, so no apt repositories.
   # Have to tell apt to use Ubuntu 18.04 Bionic's apt repositories, since that's the oldest LTS with
   # Python 3.6. This is terrible!
   RUN cp /etc/apt/sources.list /etc/apt/sources.list.old && \
       sed -i -e s/yakkety/bionic/g /etc/apt/sources.list

   # may not want to do apt-get update if there are dependencies of
   # the Kaldi image that rely on older versions of apt packages
   RUN apt-get update && \
       apt-get install -y python3 python3-pip python3-setuptools

   COPY ./ ./app
   WORKDIR ./app
   RUN pip3 install -r requirements.txt

   ENTRYPOINT ["python3"]
   CMD ["app.py"]

Since the HiPSTAS Docker image is based on Ubuntu 16.10, which is not an
LTS release, all the apt repositories are dead, so to avoid installing
things from source we just hack our way around it by pointing to the
Ubuntu 18.04 repositories. Eventually, we'll probably update this to
extend our own base image, since this is not exactly optimal.

The key information here is that when run without arguments, your
container should start up your Flask server. In this case, it runs
``python3 app.py``.
