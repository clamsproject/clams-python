import argparse
import itertools
import json
import pathlib
import sys
import textwrap
from typing import Union, Generator, List, Optional, Iterable
from urllib.parse import urlparse

from mmif import Mmif, Document, DocumentTypes, __specver__
from mmif.serialize.mmif import MmifMetadata

__all__ = ['WorkflowSource']

DOC_JSON = Union[str, dict]
DOC = Union[DOC_JSON, Document]
METADATA_JSON = Union[str, dict]
METADATA = Union[METADATA_JSON, MmifMetadata]


class WorkflowSource:
    """
    A WorkflowSource object is used at the beginning of a
    CLAMS workflow to populate a new MMIF file with media.

    The same WorkflowSource object can be used repeatedly
    to generate multiple MMIF objects.

    :param common_documents_json:
        JSON doc_lists for any documents that should be common
        to all MMIF objects produced by this workflow.

    :param common_metadata_json:
        JSON doc_lists for metadata that should be common to
        all MMIF objects produced by this workflow.
    """
    mmif: Mmif

    def __init__(
            self,
            common_documents_json: Optional[List[DOC_JSON]] = None,
            common_metadata_json: Optional[METADATA_JSON] = None
    ) -> None:
        if common_documents_json is None:
            common_documents_json = []
        if common_metadata_json is None:
            common_metadata_json = dict()
        self.mmif_start: dict = {"documents": [json.loads(document)
                                               if isinstance(document, str)
                                               else document
                                               for document in common_documents_json],
                                 "views": [],
                                 "metadata": {
                                     "mmif": f"http://mmif.clams.ai/{__specver__}",
                                     **common_metadata_json
                                 }}
        self.prime()

    def add_document(self, document: Union[str, dict, Document]) -> None:
        """
        Adds a document to the working source MMIF.

        When you're done, fetch the source MMIF with produce().

        :param document: the medium to add, as a JSON dict
                         or string or as a MMIF Medium object
        """
        if isinstance(document, (str, dict)):
            document = Document(document)
        self.mmif.add_document(document)

    def change_metadata(self, key: str, value):
        """
        Adds or changes a metadata entry in the working source MMIF.

        :param key: the desired key of the metadata property
        :param value: the desired value of the metadata property
        """
        self.mmif.metadata[key] = value

    def prime(self) -> None:
        """
        Primes the WorkflowSource with a fresh MMIF object.

        Call this method if you want to reset the WorkflowSource
        without producing a MMIF object with produce().
        """
        self.mmif = Mmif(self.mmif_start)

    def produce(self) -> Mmif:
        """
        Returns the source MMIF and resets the WorkflowSource.

        Call this method once you have added all the documents
        for your Workflow.

        :return: the current MMIF object that has been prepared
        """
        source = self.mmif
        self.prime()
        return source

    def __call__(
            self,
            documents: Optional[List[DOC]] = None,
            metadata: Optional[METADATA] = None
    ) -> Mmif:
        """
        Callable API that produces a new MMIF object from
        this workflow source given a list of documents and
        a metadata object.

        Call with no parameters to produce the default MMIF
        object from ``self.mmif_start``.

        :param documents: a list of additional documents to add
        :param metadata: additional metadata fields to add
        :return: the produced MMIF object
        """
        if documents is None:
            documents = []
        if metadata is None:
            metadata = {}

        if isinstance(documents, str):
            documents = json.loads(documents)
        if isinstance(metadata, MmifMetadata):
            metadata = metadata.serialize() # pytype: disable=attribute-error # bug in pytype? (https://github.com/google/pytype/issues/533)
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        for document in documents:
            self.add_document(document)
        for key, value in metadata.items():
            self.change_metadata(key, value)
        return self.produce()

    def from_data(
            self,
            doc_lists: Iterable[List[DOC]],
            metadata_objs: Optional[Iterable[Optional[METADATA]]] = None
    ) -> Generator[Mmif, None, None]:
        """
        Provided with an iterable of document lists and an
        optional iterable of metadata objects, generates
        MMIF objects produced from that data.

        ``doc_lists`` and ``metadata_objs`` should be matched pairwise,
        so that if they are zipped together, each pair defines
        a single MMIF object from this workflow source.

        :param doc_lists: an iterable of document lists to generate MMIF from
        :param metadata_objs: an iterable of metadata objects paired with the document lists
        :return: a generator of produced MMIF files from the data
        """
        if metadata_objs is None:
            metadata_objs = itertools.repeat(None)
        for documents, metadata in zip(doc_lists, metadata_objs):
            yield self(documents, metadata)

    def __iter__(self):
        """
        Endlessly produces MMIF directly from ``self.mmif_start``.

        If called after adding documents or changing metadata,
        these changes are discarded, as the workflow source
        gets re-primed.
        """
        self.prime()
        while True:
            yield self.produce()


def generate_source_mmif_from_file(documents, prefix=None, scheme='file', **ignored):
    at_types = {
        'video': DocumentTypes.VideoDocument,
        'audio': DocumentTypes.AudioDocument,
        'text': DocumentTypes.TextDocument,
        'image': DocumentTypes.ImageDocument
    }
    pl = WorkflowSource()
    if prefix:
        prefix = pathlib.PurePosixPath(prefix)
        if not prefix.is_absolute():
            raise ValueError(f"prefix must be an absolute path; given \"{prefix}\".")
    for doc_id, arg in enumerate(documents, start=1):
        arg = arg.strip()
        if len(arg) < 1:
            continue
        result = arg.split(':', maxsplit=1)
        if len(result) == 2 and result[0].split('/', maxsplit=1)[0] in at_types:
            mime, location = result
        else:
            raise ValueError(
                f'Invalid MIME types, or no MIME type and/or path provided, in argument {doc_id-1} to source'
            )
        location_uri = urlparse(location, scheme=scheme)
        if location_uri.scheme == 'file':
            location = pathlib.PurePosixPath(location_uri.path)
            if prefix and location.is_absolute():
                raise ValueError(f"when prefix is used, file location must not be an absolute path; given \"{location}\".")
            elif not prefix and not location.is_absolute():
                raise ValueError(f'file location must be an absolute path, or --prefix must be used; given \"{location}\".')
            elif prefix and not location.is_absolute():
                location = prefix / location
        location = str(location)
        doc = Document()
        doc.at_type = at_types[mime.split('/', maxsplit=1)[0]]
        doc.properties.location = f"{location_uri.scheme}://{location if not location.startswith(location_uri.scheme) else location[len(location_uri.scheme)+3:]}"
        doc.properties.id = f'd{doc_id}'
        doc.properties.mime = mime
        pl.add_document(doc)
    return pl.produce().serialize(pretty=True)


def describe_argparser():
    """
    returns two strings: one-line description of the argparser, and addition material, 
    which will be shown in `clams --help` and `clams <subcmd> --help`, respectively.
    """
    oneliner = 'provides CLI to create a "source" MMIF json.'
    additional = textwrap.dedent("""
    A source MMIF is a MMIF with a list of source documents but empty views. 
    It can be used as a starting point for a CLAMS workflow. """)
    return oneliner, oneliner + '\n\n' + additional


def prep_argparser(**kwargs):
    import pkgutil
    import re
    import importlib
    discovered_docloc_plugins = {
        name[len('mmif_docloc_'):]: importlib.import_module(name) for _, name, _ in pkgutil.iter_modules() if
        re.match(r'mmif[-_]docloc[-_]', name)
    }
    parser = argparse.ArgumentParser(description=describe_argparser()[1], formatter_class=argparse.RawTextHelpFormatter, **kwargs)
    parser.add_argument(
        'documents',
        default=None,
        action='store',
        nargs='+',
        help='This list of documents MUST be colon-delimited pairs of document types and file locations. A document '
             'type can be one of `audio`, `video`, `text`, `image`, or a MIME type string (such as video/mp4). The '
             'file locations MUST be valid URI strings (e.g. `file:///path/to/file.mp4`, or URI scheme part can be '
             'omitted, when `--scheme` flag is used). Note that when `file://` scheme is used (default), locations '
             'MUST BE POSIX forms (Windows forms are not supported). The output will be a MMIF file containing a '
             'document for each of those file paths, with the appropriate ``@type`` and MIME type (if given).'
    )
    parser.add_argument(
        '-p', '--prefix',
        default=None,
        metavar='PATH',
        nargs='?',
        help='An absolute path to use as prefix for file paths (ONLY WORKS with the default `file://` scheme, ignored '
             'otherwise. MUST BE a POSIX form, Windows form is not supported). If prefix is set, document file paths '
             'MUST be relative. Useful when creating source MMIF files from a system that\'s different from the '
             'environment that actually runs the workflow (e.g. in a container).'
    )
    parser.add_argument(
        '-o', '--output',
        default=None,
        action='store',
        nargs='?',
        help='A name of a file to capture a generated MMIF json. When not given, MMIF is printed to stdout.'
    )
    scheme_help = 'A scheme to associate with the document location URI. When not given, the default scheme is `file://`.'
    if len(discovered_docloc_plugins) > 0:
        plugin_help = [f'"{scheme_name}" ({scheme_plugin.help() if "help" in dir(scheme_plugin) else "help msg not provided by developer"})' 
                       for scheme_name, scheme_plugin in discovered_docloc_plugins.items()]
        scheme_help += ' (AVAILABLE ADDITIONAL SCHEMES)  ' + ', '.join(plugin_help)
    parser.add_argument(
        '-s', '--scheme',
        default='file',
        action='store',
        nargs='?',
        help=scheme_help
    )
    return parser


def main(args):
    if args.output:
        out_f = open(args.output, 'w')
    else:
        out_f = sys.stdout
    mmif = generate_source_mmif_from_file(windows_path=False, **vars(args))
    out_f.write(mmif)
    return mmif

if __name__ == '__main__':
    parser = prep_argparser()
    args = parser.parse_args()
    main(args)
