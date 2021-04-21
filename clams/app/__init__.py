from abc import ABC, abstractmethod
import json
import os
from urllib import parse as urlparser
from contextlib import contextmanager

__all__ = ['ClamsApp']

from typing import Union, Any, List

from mmif import Mmif, Document, DocumentTypes, View
from clams.appmetadata import AppMetadata, Input


class ClamsApp(ABC):
    """
    An abstract class to define API's for ClamsApps. A CLAMS app should inherit
    this class and then can be used with classes in :mod:`.restify` to work as
    web applications.
    """

    def __init__(self):
        self.metadata: AppMetadata = self._appmetadata()
        self.input_spec = self._input_spec()
        self.output_spec = self._output_spec()
        super().__init__()
        # data type specification for common parameters
        self.metadata_param_spec = {'pretty': bool}
        self.annotate_param_spec = {'pretty': bool}

    def appmetadata(self, **kwargs) -> str:
        """
        A public method to get metadata for this app as a string.

        :return: Serialized JSON string of the metadata
        """
        self.metadata.input = self.input_spec
        self.metadata.output = self.output_spec
        pretty = kwargs.pop('pretty') if 'pretty' in kwargs else False
        if pretty:
            return self.metadata.json(exclude_unset=True, by_alias=True, indent=2)
        else:
            return self.metadata.json(exclude_unset=True, by_alias=True)

    @abstractmethod
    def _input_spec(self) -> List['Input']:
        """
        An abstract method to set up input specification for this app. All CLAMS
        app must implement this.
        
        :return: a list of ``Input`` objects
        """
        raise NotImplementedError()

    @abstractmethod
    def _output_spec(self) -> List['Input']:
        """
        An abstract method to set up output specification for this app. All CLAMS
        app must implement this.
        
        :return: a list of ``Output`` objects
        """
        raise NotImplementedError()

    @abstractmethod
    def _appmetadata(self) -> AppMetadata:
        """
        An abstract method to generate (or load if stored elsewhere) the app metadata
        at runtime. All CLAMS app must implement this. Note that ``input`` and 
        ``output`` fields must be implemented separately via :func:`_input_spec` 
        and :func:`_output_spec` respectively. That is, this method should only 
        populate basic app information on the top-level of the schema. 

        :return: A Python object of the metadata, must be JSON-serializable
        """
        raise NotImplementedError()

    def annotate(self, mmif: Union[str, dict, Mmif], **kwargs) -> str:
        """
        A public method to invoke the primary app function. It's essentially a
        wrapper around :func:`~clams.app.ClamsApp._annotate` method where some common operations
        (that are invoked by keyword arguments) are implemented.

        :param mmif: An input MMIF object to annotate
        :param kwargs: An arbitrary set of k-v pairs to configure the app at runtime
        :return: Serialized JSON string of the output of the app
        """
        # TODO (krim @ 12/17/20): add documentation on what are "common" operations
        # should pop all "common" parameters before passing the args to _annotate()
        pretty = kwargs.pop('pretty') if 'pretty' in kwargs else False
        annotated = self._annotate(mmif, **kwargs)
        return annotated.serialize(pretty=pretty)

    @abstractmethod
    def _annotate(self, mmif: Union[str, dict, Mmif], **kwargs) -> Mmif:
        """
        An abstract method to generate (or load if stored elsewhere) the app metadata
        at runtime. All CLAMS app must implement this.

        :param mmif: An input MMIF object to annotate
        :param kwargs: An arbitrary set of k-v pairs to configure the app at runtime
        :return: A :class:`~mmif.serialize.mmif.Mmif` object of the annotated output, ready for serialization
        """
        raise NotImplementedError()

    def sign_view(self, view: View, parameters: dict) -> None:
        """
        A method to "sign" a new view that this app creates at the beginning of annotation.
        Signing will populate the view metadata with information and configuration of this app.
        The parameters passed to the :func:`~clams.app.ClamsApp._annotate` must be
        passed to this method. This means all parameters for "common" configuration that
        are consumed in :func:`~clams.app.ClamsApp.annotate` should not be recorded in the
        view metadata.
        :param view: a view to sign
        :param parameters: runtime configuration of the app as k-v pairs
        """
        if view.is_frozen():
            raise ValueError("can't modify an old view")
        view.metadata['app'] = self.metadata['iri']
        view.metadata['parameter'] = parameters

    @staticmethod
    def validate_document_locations(mmif: Union[str, Mmif]) -> None:
        """
        Validate files encoded in the input MMIF.

        :param mmif: An input MMIF with zero or more :class:`~mmif.serialize.annotation.Document`
        :raises FileNotFoundError: When any of files is not found at its location
        """
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
        A context-providing file opener. A user can provide their own opener
        class/method and parameters. By default, with will use python built-in
        `open` to open the location of the document.

        :param document: A :class:`~mmif.serialize.annotation.Document` object that has ``location``
        :param opener: A Python class or method that can be used to open a file (e.g. `PIL.Image <https://pillow.readthedocs.io/en/stable/reference/Image.html>`_ for an image file)
        :param openerargs: Parameters that are passed to the ``opener``
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
