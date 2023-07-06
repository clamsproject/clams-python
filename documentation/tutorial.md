# Tutorial: Wrapping an NLP Application

The following is a tutorial on how to wrap a simple NLP tool as a CLAMS application. This may not make a lot of sense without glancing over recent MMIF specifications at [https://mmif.clams.ai/](https://mmif.clams.ai/). The example in here is for CLAMS version 1.0.3 from June 2023 and version 0.0.7 of the application.

When building this application you need Python 3.6 or higher and it's necessary to install some modules, preferably in a clean Python virtual environment:

```bash
$ pip install -r requirements.txt
```

This boils down to installing version 1.0.3 of clams-python, which installs the the CLAMS code, the Python interface to the MMIF format and some third party modules like Flask and requests. It also installs the LAPPS Python interface, which is relevant to most NLP applications.

### 1.  The NLP tool

We use an ultra simple tokenizer in `tokenizer.py` as the example NLP tool. All it does is define a tokenize function that uses a simple regular expression and returns a list of offset pairs.

```python {.line-numbers}
def tokenize(text):
    return [tok.span() for tok in re.finditer("\w+", text)]
```

```python
>>> import tokenizer
>>> tokenizer.tokenize('Fido barks.')
[(0, 4), (5, 10)]
```



### 2.  Wrapping the tokenizer

By convention, all the wrapping code is in a script named `app.py`, but this is not a strict requirement and you can give it another name. The `app.py` script does several things: (1) import the necessary code, (2) create a subclass of `ClamsApp` that defines the metadata and provides a method to run the wrapped NLP tool, and (3) provide a way to run the code as a RESTful Flask service. The most salient parts of the code are explained here.

First, it is recommended to call `clams develop` in the command line and follow the instructions there to generate the necessary skeleton templates for developing the app. These include templates for the aforementioned `app.py` and `metadata.py`, which contains its own method for defining the metadata of the app.

##### Imports

Aside from a few standard modules we need the following imports:

```python
from clams.app import ClamsApp
from clams.restify import Restifier
from clams.appmetadata import AppMetadata
from mmif.serialize import Mmif
from mmif.vocabulary import DocumentTypes
from lapps.discriminators import Uri
import tokenizer
```

For non-NLP CLAMS applications we would also do  `from mmif.vocabulary import AnnotationTypes`, but this is not needed for NLP applications because they do not need the CLAMS vocabulary. What we do need to import are the URIs of all LAPPS annotation types and the NLP tool itself.

Importing `lapps.discriminators.Uri` is for convenience since it gives us easy acces to the URIs of annotation types and some of their attributes. The following code prints a list of available variables that point to URIs:

```python
>>> from lapps.discriminators import Uri
>>> attrs = [x for x in dir(Uri) if not x.startswith('__')]
>>> attrs = [a for a in attrs if not getattr(Uri, a).find('org/ns') > -1]
>>> print(' '.join(attrs))
ANNOTATION CHUNK CONSTITUENT COREF DATE DEPENDENCY DEPENDENCY_STRUCTURE DOCUMENT GENERIC_RELATION LEMMA LOCATION LOOKUP MARKABLE MATCHES NCHUNK NE ORGANIZATION PARAGRAPH PERSON PHRASE_STRUCTURE POS RELATION SEMANTIC_ROLE SENTENCE TOKEN VCHUNK
```

##### The application class

With the imports in place we define a subclass of `ClamsApp` which needs two methods:

```python
class TokenizerApp(ClamsApp):
    def _appmetadata(self): pass
    
    def _annotate(self, mmif): pass
```

Here it is useful to introduce some background. The CLAMS RESTful API connects the GET and POST methods to the `appmetdata()`  and  `annotate()` methods on the app, and those methods are both defined in `ClamsApp`. In essence, they are wrappers around  `_appmetadata()` and   `_annotate()` and provide some common functionality like making sure the output is serialized into a string.

The `_appmetadata()` method should return an `AppMetadata` object that defines the relevant metadata for the app: 


```python
def _appmetadata(self):
    metadata = AppMetadata(
        identifier='https://apps.clams.ai/tokenizer',
        url='https://github.com/clamsproject/app-nlp-example',
        name="Simplistic Tokenizer",
        description="Apply simple tokenization to all text documents in a MMIF file.",
        app_version=APP_VERSION,
        app_license=APP_LICENSE,
        analyzer_version=TOKENIZER_VERSION,
        analyzer_license=TOKENIZER_LICENSE,
        mmif_version=MMIF_VERSION
    )
    metadata.add_input(DocumentTypes.TextDocument)
    metadata.add_output(Uri.TOKEN)
    metadata.add_parameter('error', 'Throw error if set to True', 'boolean')
    metadata.add_parameter('eol', 'Insert sentence boundaries', 'boolean')
    return metadata
```

The variables used in the code above are defined closer to the top of the file:

```python
APP_VERSION = '0.0.7'
MMIF_VERSION = '1.0.0'
MMIF_PYTHON_VERSION = '1.0.1'
CLAMS_PYTHON_VERSION = '1.0.3'
TOKENIZER_VERSION = tokenizer.__VERSION__

APP_LICENSE = 'Apache 2.0'
TOKENIZER_LICENSE = 'Apache 2.0'
```

The MMIF_PYTHON_VERSION and CLAMS_PYTHON_VERSION variables are technically not needed since they are implied by using `pip install clams-python==1.0.3`, but I find it helpful to name them explicitly.

__Note__: When using the separately generated `metadata.py` created via `clams develop`, this method within `app.py` should be left empty with a `pass` statement as shown below:

```python
def _appmetadata(self):
    # When using the ``metadata.py`` leave this do-nothing "pass" method here. 
        pass
```

And the `appmetadata()` within `metadata.py` should be implemented instead. Follow the instructions in the template. Also refer to [CLAMS App Metadata](https://sdk.clams.ai/appmetadata.html) for more details regarding what fields need to be specified.

The `_annotate()` method should accept a MMIF file as its parameter and always returns a `MMIF` object with an additional `view` containing annotation results. This is where the bulk of your logic will go. For a text processing app, it is mostly concerned with finding text documents, calling the code that runs over the text, creating new views and inserting the results.

```python
def _annotate(self, mmif, **kwargs):
    # some example code to show how to access parameters, here to just print
    # them and to willy-nilly throw an error if the caller wants that
    for arg, val in kwargs.items():
        print("Parameter %s=%s" % (arg, val))
        if arg == 'error' and val is True:
            raise Exception("Exception - %s" % kwargs['error'])
    # reset identifier counts for each annotation
    Identifiers.reset()
    # Initialize the MMIF object from the string if needed
    self.mmif = mmif if type(mmif) is Mmif else Mmif(mmif)
    # process the text documents in the documents list
    for doc in text_documents(self.mmif.documents):
        new_view = self._new_view(doc.id)
        self._run_nlp_tool(doc, new_view, doc.id)
    # process the text documents in all the views, we copy the views into a
    # list because self.mmif.views will be changed
    for view in list(self.mmif.views):
        docs = self.mmif.get_documents_in_view(view.id)
        if docs:
            new_view = self._new_view()
            for doc in docs:
                doc_id = view.id + ':' + doc.id
                self._run_nlp_tool(doc, new_view, doc_id)
    # return the MMIF object
    return self.mmif
```

For language processing applications, one task is to retrieve all text documents from both the documents list and the views. Annotations generated by the NLP tool need to be anchored to the text documents, which in the case of text documents in the documents list is done by using the text document identifier, but for text documents in views we also need the view identifier. A view may have many text documents and typically all annotations created will be put in one view.

For each text document from the document list, there is one invocation of `_new_view()` which gets handed a document identifier so it can be put in the view metadata. And for each view with text documents there is also one invocation of `_new_view()`, but no document identifier is handed in so the identifier will not be put into the view metadata.

The method  `_run_nlp_tool()` is responsible for running the NLP tool and adding annotations to the new view. The third argument allows us to anchor annotations created by the tool by handing over the document identifier, possibly prefixed by the view the document lives in.

One thing about `_annotate()` as it is defined above is that it will most likely be the same for each NLP application, all the application specific details are in the code that creates new views and the code that adds annotations.

Creating a new view:

```python
def _new_view(self, docid=None):
    view = self.mmif.new_view()
    view.metadata.app = self.metadata.identifier
    self.sign_view(view)
    view.new_contain(Uri.TOKEN, document=docid)
    return view
```

This is the simplest NLP view possible since there is only one annotation type and it has no metadata properties beyond the `document` property. Other applications may have more annotation types, which results in repeated invocations of `new_contain()`, and may define other metadata properties for those types.

Adding annotations:

```python
def _run_nlp_tool(self, doc, new_view, full_doc_id):
    """Run the NLP tool over the document and add annotations to the view, using the
    full document identifier (which may include a view identifier) for the document
    property."""
    text = self._read_text(doc)
    tokens = tokenizer.tokenize(text)
    for p1, p2 in tokens:
        a = new_view.new_annotation(Uri.TOKEN, Identifiers.new("t"))
        # no need to do this for documents in the documents list
        if ':' in full_doc_id:
            a.add_property('document', full_doc_id)
        a.add_property('start', p1)
        a.add_property('end', p2)
        a.add_property('text', text[p1:p2])
```

First, with `_read_text()` we get the text from the text document, either from its `location` property or from its `text`property. Second, we apply the tokenizer to the text. And third, we loop over the token offsets in the tokenizer result and create annotations of type `Uri.TOKEN` with an identfier that is generated using the `Identifiers` class. All that is needed for adding an annotation is the `add_annotation()` method on the view object and the `add_property()` method on the annotation object.

##### Running a server

We use the CLAMS RESTful API. To run the application as a Flask server use the `run()` method:


```python
tokenizer_app = TokenizerApp()
tokenizer_service = Restifier(tokenizer_app)
tokenizer_service.run()
```

And to run it in production mode using `gunicorn` use the `serve_production()` method:


```python
tokenizer_app = TokenizerApp()
tokenizer_service = Restifier(tokenizer_app)
tokenizer_service.serve_production()
```

On the command line these correspond to the following two invocations:

```bash
$ python app.py --develop
$ python app.py
```

The first one is for a development server, the second for a production server.

### 3.  Testing the application

There are two ways to test the application. The first is to use the `test.py` script, which will just test the wrapping code without using Flask:

```bash
$ python test.py input/example-1.mmif out.json
```

When you run this the `out.json` file should be about 10K in size and contain pretty printed JSON. And at the same time something like the following should be printed to the standard output:

```
<View id=v_1 annotations=2 app=http://mmif.clams.ai/apps/east/0.2.1>
<View id=v_2 annotations=4 app=http://mmif.clams.ai/apps/tesseract/0.2.1>
<View id=v_3 annotations=24 app=https://apps.clams.ai/tokenizer>
<View id=v_4 annotations=6 app=https://apps.clams.ai/tokenizer>
```

The second way tests the behavior of the application in a Flask server by running the application as a service in one terminal:

```bash
$ python app.py --develop
```

And poking at it from another:

```bash
$ curl http://0.0.0.0:5000/
$ curl -H "Accept: application/json" -X POST -d@input/example-1.mmif http://0.0.0.0:5000/
```

The first one prints the metadata and the second the output MMIF file. Appending `?pretty=True` to the URL will result in pretty printed output. Note that with the `--develop` option we started a Flask development server, without the option a production server will be started.

Some notes on the example input MMIF file. It has two documents in its `documents` list, a video document and a text document. The text document has the text inline in a text value field. You could also give it a location as follows (see `input/example-2.mmif`).

```json
{
  "@type": "http://mmif.clams.ai/0.4.0/vocabulary/TextDocument",
  "properties": {
    "id": "m2",
    "mime": "text/plain",
    "location": "file:///var/archive/text/example.txt"
}
```

The location has to be URL or an absolute path and it is your resonsibility to make sure it exists. Note that the video document in the example defines a path to an mp4 file which most likely does not exist. This is not hurting us because at no time are we accessing that location.



### 4.  Configuration files and Docker

Apps within CLAMS typically run as Flask servers in Docker containers, and after an app is tested as a local Flask application it should be dockerized. In fact, in some cases we don't even bother running a local Flask server and move straight to the Docker set up.

Three configuration files for building a Docker image should be automatically generated through the `clams develop` command:

| file             | description                                                  |
| ---------------- | :----------------------------------------------------------- |
| Containerfile    | Describes how to create a Docker image for this application. |
| .dockerignore    | Specifies which files are not needed for running this application. |
| requirements.txt | File with all Python modules that need to be installed.      |

Here is the minimal Dockerfile included with this example:

```dockerfile
FROM ghcr.io/clamsproject/clams-python:$CLAMS_VERSION
WORKDIR ./app
COPY ./ ./
CMD ["python3", "app.py"]
```

This starts from the basic CLAMS Docker image which is created from an offficial Python image with the clams-python package and the code it depends on added. The Dockerfile only needs to be edited if additional installations are required to run the NLP tool. In that case the Dockerfile will have a few more lines:

```dockerfile
FROM ghcr.io/clamsproject/clams-python:$CLAMS_VERSION
WORKDIR ./app
COPY ./requirements.txt .
RUN pip3 install -r requirements.txt
COPY ./ ./
CMD ["python3", "app.py"]
```

With this Containerfile you typically only need to make changes to the requirements file for additional python installs.

This repository also includes a `.dockerignore` file. Editing it is optional, but with large repositories with lots of documentation and images you may want to add some file paths just to keep the image as small as possible.

Use one of the following commands to build the Docker image, the first one builds an image with a production server using Gunicorn, the second one builds a development server using Flask.

```bash
$ docker build -t clams-nlp-example:0.0.7 .
$ docker build -t clams-nlp-example:0.0.7-dev -f Containerfile.dev .
```

The -t option lets you pick a name and a tag for the image. You can use another name if you like. You do not have to add a tag and you could just use `-t nlp-clams-example`, but it is usually a good idea to use the version name as the tag.

To test the Flask app in the container do

```bash
$ docker run --rm -it clams-nlp-example:0.0.7 bash
```

You are now running a bash shell in the container and in the container you can run

```
root@c85a08b22f18:/app# python test.py input/example-1.mmif out.json
```

Escape out of the container with Ctrl-d.

To test the Flask app in the container from your local machine do

```bash
$ docker run --name clams-nlp-example --rm -d -p 5000:5000 clams-nlp-example:0.0.7
```

The `--name` option gives a name to the container which we use later to stop it (if we do not name the container then Docker will generate a name and we have to query docker to see what containers are running and then use that name to stop it). Now you can use curl to send requests (not sending the -h headers for brevity, it does work without them):

```bash
$ curl http://0.0.0.0:5000/
$ curl -X POST -d@input/example-1.mmif http://0.0.0.0:5000/
```

##### Using the location property

In the previous section we mentioned that instead of having the text inline you can also use the location property to point to a text file. This will not work with the set up laid out above because that's dependent on having a local path on your machine and the Docker container has no access to that path. What you need to do is to make sure that the container can see the data on your local machine and you can use the `-v` option for that:

```bash
$ docker run --name clams-nlp-example --rm -d -p 5000:5000 -v $PWD/input/data:/data clams-nlp-example:0.0.7
```

We now have specified that the `/data ` directory on the container is mounted to the `input/data` directory in the repository. Now you need to make sure that the input MMIF file uses the path on the container:

```json
{
  "@type": "http://mmif.clams.ai/0.4.0/vocabulary/VideoDocument",
  "properties": {
    "id": "m1",
    "mime": "text/plain",
    "location": "/data/text/example.txt"
}
```

And now you can use curl again

```bash
$ curl -X POST -d@input/example-3.mmif http://0.0.0.0:5000/
```
