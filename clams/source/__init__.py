import json
import itertools
from typing import Union, Generator, List, Optional, Iterable

from mmif import Mmif, Document, __specver__
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
