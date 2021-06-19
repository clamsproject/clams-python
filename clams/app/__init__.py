import os
import sys
from abc import ABC, abstractmethod
from contextlib import contextmanager
from urllib import parse as urlparser

__all__ = ['ClamsApp']

from typing import Union, Any, Optional

from mmif import Mmif, Document, DocumentTypes, View, __specver__
from clams.appmetadata import AppMetadata


class ClamsApp(ABC):
    """
    An abstract class to define API's for ClamsApps. A CLAMS app should inherit
    this class and then can be used with classes in :mod:`.restify` to work as
    web applications.
    """

    def __init__(self):
        self.metadata: AppMetadata = self._appmetadata()
        super().__init__()
        # data type specification for common parameters
        self.metadata_param_spec = {'pretty': bool}
        self.annotate_param_spec = {'pretty': bool}
        python_type = {"boolean": bool, "number": float, "integer": int, "string": str}
        for param_spec in self.metadata.parameters:
            self.annotate_param_spec[param_spec.name] = python_type[param_spec.type]

    def appmetadata(self, **kwargs) -> str:
        """
        A public method to get metadata for this app as a string.

        :return: Serialized JSON string of the metadata
        """
        pretty = kwargs.pop('pretty') if 'pretty' in kwargs else False
        if pretty:
            return self.metadata.json(exclude_defaults=True, by_alias=True, indent=2)
        else:
            return self.metadata.json(exclude_defaults=True, by_alias=True)

    @abstractmethod
    def _appmetadata(self) -> AppMetadata:
        """
        An abstract method to generate (or load if stored elsewhere) the app metadata
        at runtime. All CLAMS app must implement this. For metadata specification, 
        see `https://sdk.clams.ai/appmetadata.jsonschema <../appmetadata.jsonschema>`_. 

        :return: A Python object of the metadata, must be JSON-serializable
        """
        raise NotImplementedError()

    @staticmethod
    def _check_mmif_compatibility(target_specver, input_specver):
        return target_specver.split('.')[:2] == input_specver.split('.')[:2]

    def annotate(self, mmif: Union[str, dict, Mmif], **runtime_params) -> str:
        """
        A public method to invoke the primary app function. It's essentially a
        wrapper around :func:`~clams.app.ClamsApp._annotate` method where some common operations
        (that are invoked by keyword arguments) are implemented.

        :param mmif: An input MMIF object to annotate
        :param runtime_params: An arbitrary set of k-v pairs to configure the app at runtime
        :return: Serialized JSON string of the output of the app
        """
        # TODO (krim @ 12/17/20): add documentation on what are "common" operations
        # should pop all "common" parameters before passing the args to _annotate()
        pretty = runtime_params.pop('pretty') if 'pretty' in runtime_params else False
        if not isinstance(mmif, Mmif):
            mmif = Mmif(mmif)
        input_specver = mmif.metadata.mmif.rsplit('/')[-1]  # pytype: disable=attribute-error
        if 'dev' not in __specver__ :
            if not self._check_mmif_compatibility(__specver__, input_specver):
                raise ValueError(f"Input MMIF file (versioned: {input_specver} is not compatible with the app "
                                 f"targeting at {__specver__}. Make sure apps in the pipeline is all compatible. See "
                                 f"https://mmif.clams.ai/versioning/ for information about MMIF compatibility. ") 
        annotated = self._annotate(mmif, **runtime_params)
        return annotated.serialize(pretty=pretty)

    @abstractmethod
    def _annotate(self, mmif: Union[str, dict, Mmif], **runtime_params) -> Mmif:
        """
        An abstract method to generate (or load if stored elsewhere) the app metadata
        at runtime. All CLAMS app must implement this.

        :param mmif: An input MMIF object to annotate
        :param runtime_params: An arbitrary set of k-v pairs to configure the app at runtime
        :return: A :class:`~mmif.serialize.mmif.Mmif` object of the annotated output, ready for serialization
        """
        raise NotImplementedError()
    
    def get_configuration(self, **runtime_params):
        conf = {}
        for parameter in self.metadata.parameters:
            if parameter.name in runtime_params:
                conf[parameter.name] = str(runtime_params[parameter.name])
            elif parameter.default:
                conf[parameter.name] = parameter.default
            else:
                raise ValueError(f"Cannot find configuration for parameter \"{parameter.name}\".")
        return conf

    def sign_view(self, view: View, runtime_conf: dict = None) -> None:
        """
        A method to "sign" a new view that this app creates at the beginning of annotation.
        Signing will populate the view metadata with information and configuration of this app.
        The parameters passed to the :func:`~clams.app.ClamsApp._annotate` must be
        passed to this method. This means all parameters for "common" configuration that
        are consumed in :func:`~clams.app.ClamsApp.annotate` should not be recorded in the
        view metadata.
        :param view: a view to sign
        :param runtime_conf: runtime configuration of the app as k-v pairs
        """
        if view.is_frozen():
            raise ValueError("can't modify an old view")
        view.metadata.app = self.metadata.identifier
        if runtime_conf is not None:
            view.metadata.add_parameters(**{k: str(v) for k, v in runtime_conf.items()})
        
    def set_error_view(self, mmif: Union[str, dict, Mmif], runtime_conf: dict = None) -> Mmif:
        """
        A method to record an error instead of annotation results in the view
        this app generated. For logging purpose, the runtime parameters used
        when the error occurred must be passed as well.

        :param mmif: input MMIF object
        :param runtime_conf: parameters passed to annotate when the app encountered the error
        :return: An output MMIF with a new view with the error encoded in the view metadata
        """
        import traceback
        if isinstance(mmif, str) or isinstance(mmif, dict):
            mmif = Mmif(mmif)
        error_view: Optional[View] = None
        for view in reversed(mmif.views):
            if view.metadata.app == self.metadata.identifier:
                error_view = view
                break
        if error_view is None:
            error_view = mmif.new_view()
            self.sign_view(error_view, runtime_conf)
        exc_info = sys.exc_info()
        error_view.set_error(f'{exc_info[0]}: {exc_info[1]}',
                             '\t\n'.join(traceback.format_tb(exc_info[2])))
        return mmif
    
    record_error = set_error_view

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
