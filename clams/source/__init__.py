import json
from typing import Union, List, Optional

from mmif import Mmif, Document
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
        self.mmif_start: dict = {"documents": [json.loads(document)
                                               if isinstance(document, str)
                                               else document
                                               for document in common_documents_json],
                                 "views": [],
                                 "metadata": common_metadata_json}
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
