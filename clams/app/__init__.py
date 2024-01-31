import logging
import os
import pathlib
import sys
import warnings
from abc import ABC, abstractmethod
from contextlib import contextmanager
from urllib import parse as urlparser

__all__ = ['ClamsApp']

from typing import Union, Any, Optional

from mmif import Mmif, Document, DocumentTypes, View
from clams.appmetadata import AppMetadata

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)s %(levelname)-8s %(thread)d %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")


class ClamsApp(ABC):
    """
    An abstract class to define API's for ClamsApps. A CLAMS app should inherit
    this class and then can be used with classes in :mod:`.restify` to work as
    web applications.
    """
    # A set of "universal runtime parameters that can be used for both GET and POST anytime".
    # The behavioral changes based on these parameters must be implemented on the SDK level. 
    universal_parameters = [
        {
            'name': 'pretty', 'type': 'boolean', 'choices': None, 'default': False, 'multivalued': False,
            'description': 'The JSON body of the HTTP response will be re-formatted with 2-space indentation',
        },
    ]
    # this key is used to store users' raw input params in the parameter dict 
    # even after "refinement" (i.e., casting to proper data types)
    _RAW_PARAMS_KEY = "#RAW#"

    def __init__(self):
        self.metadata: AppMetadata = self._load_appmetadata()
        super().__init__()
        # data type specification for common parameters
        python_type = {"boolean": bool, "number": float, "integer": int, "string": str}

        self.metadata_param_spec = {}
        self.annotate_param_spec = {}
        for param in ClamsApp.universal_parameters:
            self.metadata.add_parameter(**param)
            self.metadata_param_spec[param['name']] = (python_type[param['type']], param.get('multivalued', False))
        for param_spec in self.metadata.parameters:
            self.annotate_param_spec[param_spec.name] = (python_type[param_spec.type], param_spec.multivalued)
        self.logger = logging.getLogger(self.metadata.identifier)
        
    def appmetadata(self, **kwargs) -> str:
        """
        A public method to get metadata for this app as a string.

        :return: Serialized JSON string of the metadata
        """
        pretty = kwargs.pop('pretty') if 'pretty' in kwargs else False
        return self.metadata.jsonify(pretty)
    
    def _load_appmetadata(self) -> AppMetadata:
        """
        A private method to load the app metadata. This is called in __init__, 
        (only once) and it uses three sources to load the metadata (in the order 
        of priority):
        
        #. using a ``metadata.py`` file (recommended)
        #. using self._appmetadata() method (legacy, no longer recommended)
        
        In any case, :class:`~clams.appmetadata.AppMetadata` class must be useful.
        
        For metadata specification, 
        see `https://sdk.clams.ai/appmetadata.jsonschema <../appmetadata.jsonschema>`_. 
        """
        cwd = pathlib.Path(sys.modules[self.__module__].__file__).parent
        
        if (cwd / 'metadata.py').exists():
            import metadata as metadatapy  # pytype: disable=import-error
            metadata = metadatapy.appmetadata()
        else:
            metadata = self._appmetadata()
        return metadata

    @abstractmethod
    def _appmetadata(self) -> AppMetadata:
        """
        An abstract method to generate the app metadata. 

        :return: A Python object of the metadata, must be JSON-serializable
        """
        raise NotImplementedError()

    @staticmethod
    def _check_mmif_compatibility(target_specver, input_specver):
        return target_specver.split('.')[:2] == input_specver.split('.')[:2]

    def annotate(self, mmif: Union[str, dict, Mmif], **runtime_params) -> str:
        """
        A public method to invoke the primary app function. It's essentially a
        wrapper around :meth:`~clams.app.ClamsApp._annotate` method where some common operations
        (that are invoked by keyword arguments) are implemented.

        :param mmif: An input MMIF object to annotate
        :param runtime_params: An arbitrary set of k-v pairs to configure the app at runtime
        :return: Serialized JSON string of the output of the app
        """
        pretty = runtime_params.get('pretty', False)
        if not isinstance(mmif, Mmif):
            mmif = Mmif(mmif)
        issued_warnings = []
        for key in runtime_params:
            if key not in self.annotate_param_spec:
                issued_warnings.append(UserWarning(f'An undefined parameter "{key}" (value: "{runtime_params[key]}") is passed'))
        refined_params = self._refine_params(**runtime_params)
        with warnings.catch_warnings(record=True) as ws:
            annotated = self._annotate(mmif, **refined_params)
            if ws:
                issued_warnings.extend(ws)
        if issued_warnings:
            warnings_view = annotated.new_view()
            self.sign_view(warnings_view, refined_params)
            warnings_view.metadata.warnings = issued_warnings
        return annotated.serialize(pretty=pretty, sanitize=True)

    @abstractmethod
    def _annotate(self, mmif: Mmif, _raw_parameters=None, **refined_parameters) -> Mmif:
        """
        An abstract method to generate (or load if stored elsewhere) the app 
        metadata at runtime. All CLAMS app must implement this.
        
        This is where the bulk of your logic will go.
        A typical implementation of this method would be 
        
        #. Create a new view (or views) by calling :meth:`~mmif.serialize.mmif.Mmif.new_view` on the input mmif object.
        #. Call :meth:`~clams.app.ClamsApp.sign_view` with the input runtime parameters for the record.
        #. Call :meth:`~clams.app.ClamsApp.get_configuration` to get an "upgraded" runtime parameters with default values.
        #. Call :meth:`~mmif.serialize.view.View.new_contain` on the new view object with any annotation properties specified by the configuration.
        #. Process the data and create :class:`~mmif.serialize.annotation.Annotation` objects and add them to the new view. 
        #. While doing so, get help from :class:`~mmif.vocabulary.document_types.DocumentTypes`, :class:`~mmif.vocabulary.annotation_types.AnnotationTypes` classes to generate ``@type`` strings.
        #. Return the mmif object

        :param mmif: An input MMIF object to annotate
        :param runtime_params: An arbitrary set of k-v pairs to configure the app at runtime
        :return: A :class:`~mmif.serialize.mmif.Mmif` object of the annotated output, ready for serialization
        """
        raise NotImplementedError()
    
    def _refine_params(self, **runtime_params):
        """
        Method to "fill" the parameter dictionary with default values, when a key-value is not specified in the input.
        The input map is not really "filled" as a copy of it is returned with addition of default values. 
        :param runtime_params: key-value pairs of runtime parameters
        :return: a copy of parameter map, with default values added
        :raises ValueError: when a value for a required parameter is not found in the input
        """
        if self._RAW_PARAMS_KEY in runtime_params:
            # meaning the dict is already refined, just return it 
            return runtime_params
        conf = {}
        for parameter in self.metadata.parameters:
            if parameter.name in runtime_params:
                if parameter.choices and runtime_params[parameter.name] not in parameter.choices:
                    raise ValueError(f"Value for parameter \"{parameter.name}\" must be one of {parameter.choices}.")
                conf[parameter.name] = runtime_params[parameter.name]
            elif parameter.default is not None:
                conf[parameter.name] = parameter.default
            else:
                raise ValueError(f"Cannot find configuration for a required parameter \"{parameter.name}\".")
        # raw input params are hidden under a special key
        conf[self._RAW_PARAMS_KEY] = runtime_params
        return conf
    
    def get_configuration(self, **runtime_params):
        warnings.warn("ClamsApp.get_configuration() is deprecated. "
                      "If you are using this method in `_annotate()` method,"
                      "it is no longer needed since `clams-python==1.0.10`.", 
                      DeprecationWarning, stacklevel=2)
        return self._refine_params(**runtime_params)

    def sign_view(self, view: View, runtime_conf: Optional[dict] = None) -> None:
        """
        A method to "sign" a new view that this app creates at the beginning of annotation.
        Signing will populate the view metadata with information and configuration of this app.
        The parameters passed to the :meth:`~clams.app.ClamsApp._annotate` must be
        passed to this method. This means all parameters for "common" configuration that
        are consumed in :meth:`~clams.app.ClamsApp.annotate` should not be recorded in the
        view metadata.
        :param view: a view to sign
        :param runtime_conf: runtime configuration of the app as k-v pairs
        """
        # TODO (krim @ 8/2/23): once all devs understood this change, make runtime_conf a required argument
        if runtime_conf is None:
            warnings.warn("`runtime_conf` argument for ClamsApp.sign_view() will "
                          "no longer be optional in the future. Please just pass "
                          "`runtime_params` from _annotate() method.",
                          FutureWarning, stacklevel=2)
        view.metadata.app = self.metadata.identifier
        if runtime_conf is not None:
            if self._RAW_PARAMS_KEY in runtime_conf:
                conf = runtime_conf[self._RAW_PARAMS_KEY]
            else:
                conf = runtime_conf
            view.metadata.add_parameters(**{k: str(v) for k, v in conf.items()})
            # TODO (krim @ 8/2/23): add "refined" parameters as well 
            #  once https://github.com/clamsproject/mmif/issues/208 is resolved
        
    def set_error_view(self, mmif: Union[str, dict, Mmif], runtime_conf: Optional[dict] = None) -> Mmif:
        """
        A method to record an error instead of annotation results in the view
        this app generated. For logging purpose, the runtime parameters used
        when the error occurred must be passed as well.

        :param mmif: input MMIF object
        :param runtime_conf: parameters passed to annotate when the app encountered the error
        :return: An output MMIF with a new view with the error encoded in the view metadata
        """
        import traceback
        if isinstance(mmif, bytes) or isinstance(mmif, str) or isinstance(mmif, dict):
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
