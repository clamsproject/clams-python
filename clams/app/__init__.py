from abc import ABC, abstractmethod
import json
import os
from urllib import parse as urlparser
from contextlib import contextmanager


__all__ = ['ClamsApp']

from typing import Union, Any

from mmif import Mmif, Document, DocumentTypes


class ClamsApp(ABC):
    def __init__(self):
        # TODO (krim @ 10/9/20): eventually we might end up with a python class
        # for this metadata (with a JSON schema)
        self.metadata: dict = self._appmetadata()
        super().__init__()

    def appmetadata(self) -> str:
        # TODO (krim @ 10/9/20): when self.metadata is no longer a `dict`
        # this method might needs to be changed to properly serialize input
        return json.dumps(self.metadata)

    @abstractmethod
    def _appmetadata(self) -> dict:
        raise NotImplementedError()

    def annotate(self, mmif: Union[str, dict, Mmif], **kwargs) -> str:
        """
        A wrapper around ``_annotate`` method where some common operations invoked by kwargs are implemented.

        :param mmif:
        :param kwargs:
        :return:
        """
        # TODO (krim @ 12/17/20): add documentation on what are "common" operations

        # popping
        pretty = kwargs.pop('pretty') if 'pretty' in kwargs else False
        annotated = self._annotate(mmif, **kwargs)
        return annotated.serialize(pretty=pretty)

    @abstractmethod
    def _annotate(self, mmif: Union[str, dict, Mmif], **kwargs) -> Mmif:
        raise NotImplementedError()

    @staticmethod
    def validate_document_locations(mmif: Union[str, Mmif]) -> None:
        if isinstance(mmif, str):
            mmif = Mmif(mmif)
        for document in mmif.documents:
            loc = document.location
            if loc is not None and len(loc) > 0:
                p = urlparser.urlparse(loc)
                if p.scheme == 'file':
                    if os.path.exists(p.path):
                        raise FileNotFoundError(f'{document.id}: {loc}')
                # TODO (krim @ 12/15/20): with implementation of file checksum
                #  (https://github.com/clamsproject/mmif/issues/150) , here is a good place for additional check for
                #  file integrity

    @staticmethod
    @contextmanager
    def open_document_location(document: Union[str, Document], opener: Any = open, **openerargs):
        """
        A context-providing file opener. User can provide their own opening class/method and parameters.
        By default, with will use python built-in `open` to open the location of the document.
        :param document:
        :param opener:
        :return:
        """
        if isinstance(document, str):
            document = Document(document)
        if document.location is not None and len(document.location) > 0:
            p = urlparser.urlparse(document.location)
            if p.scheme == 'file':
                if os.path.exists(p.path):
                    if 'mode' not in openerargs and document.at_type == DocumentTypes.TextDocument:
                        openerargs['mode'] = 'r'
                    document_file = opener(p.path, **openerargs)
                    try:
                        yield document_file
                    finally:
                        document_file.close()
                else:
                    raise FileNotFoundError(p.path)