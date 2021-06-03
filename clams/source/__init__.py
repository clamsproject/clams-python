import argparse
import json
import itertools
from os import path
from typing import Union, Generator, List, Optional, Iterable

from mmif import Mmif, Document, DocumentTypes, __specver__
from mmif.serialize.mmif import MmifMetadata


__all__ = ['PipelineSource']

DOC_JSON = Union[str, dict]
DOC = Union[DOC_JSON, Document]
METADATA_JSON = Union[str, dict]
METADATA = Union[METADATA_JSON, MmifMetadata]


class PipelineSource:
    """
    The PipelineSource class.

    A PipelineSource object is used at the beginning of a
    CLAMS pipeline to populate a new MMIF file with media.

    The same PipelineSource object can be used repeatedly
    to generate multiple MMIF objects.

    :param common_documents_json:
        JSON doc_lists for any documents that should be common
        to all MMIF objects produced by this pipeline.

    :param common_metadata_json:
        JSON doc_lists for metadata that should be common to
        all MMIF objects produced by this pipeline.
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
        Primes the PipelineSource with a fresh MMIF object.

        Call this method if you want to reset the PipelineSource
        without producing a MMIF object with produce().
        """
        self.mmif = Mmif(self.mmif_start, frozen=False)

    def produce(self) -> Mmif:
        """
        Returns the source MMIF and resets the PipelineSource.

        Call this method once you have added all the documents
        for your pipeline.

        :return: the current MMIF object that has been prepared
        """
        source = self.mmif
        source.freeze_documents()
        self.prime()
        return source

    def __call__(
            self,
            documents: Optional[List[DOC]] = None,
            metadata: Optional[METADATA] = None
    ) -> Mmif:
        """
        Callable API that produces a new MMIF object from
        this pipeline source given a list of documents and
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
        a single MMIF object from this pipeline source.

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
        these changes are discarded, as the pipeline source
        gets re-primed.
        """
        self.prime()
        while True:
            yield self.produce()


def prep_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'documents',
        default='',
        action='store',
        nargs='+',
        help="This list of documents should be colon-joined pairs of document types and file paths. A document type "
             "can be one of ``audio``, ``video``, ``text``, ``image``, or a MIME type string (such as video/mp4). The "
             "output will be a MMIF file containing a document for each of those file paths, with the appropriate "
             "``@type`` and MIME type (if given), printed to the standard output. "
    )
    parser.add_argument(
        '-p', '--prefix',
        default=None,
        metavar='PATH',
        nargs='?',
        help='An absolute path to use as prefix for document file paths. When prefix is set, document file paths MUST '
             'be relative. This can be useful when creating source MMIF files from a system that\'s different from '
             'the system that actually runs the pipeline (e.g. in a docker container).'
    )
    return parser


def generate_source_mmif(documents, prefix=None):
    from string import Template
    at_types = {
        'video': DocumentTypes.VideoDocument,
        'audio': DocumentTypes.AudioDocument,
        'text': DocumentTypes.TextDocument,
        'image': DocumentTypes.ImageDocument
    }
    template = Template('''{
          "@type": "${at_type}",
          "properties": {
            "id": "${aid}",
            "mime": "${mime}",
            "location": "${location}" }
        }''')
    pl = PipelineSource()
    if prefix and not path.isabs(prefix):
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
        if prefix and path.isabs(location):
            raise ValueError(f"when prefix is used, file location must not be an absolute path; given \"{location}\".")
        elif not prefix and not path.isabs(location):
            raise ValueError(f'file location must be an absolute path, or --prefix must be used; given \"{location}\".')
        elif prefix and not path.isabs(location):
            location = path.join(prefix, location)
        doc = template.substitute(
            at_type=str(at_types[mime.split('/', maxsplit=1)[0]]),
            aid=f'd{doc_id}',
            mime=mime,
            location=location
        )
        pl.add_document(doc)
    return pl.produce().serialize(pretty=True)


if __name__ == '__main__':
    parser = prep_argparser()
    args = parser.parse_args()
    print(generate_source_mmif(**vars(args)))