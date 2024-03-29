import logging
import os
import pathlib
import sys
import warnings
from abc import ABC, abstractmethod
from contextlib import contextmanager
from urllib import parse as urlparser

__all__ = ['ClamsApp']

from typing import Union, Any, Optional, Dict, List, Iterable

from mmif import Mmif, Document, DocumentTypes, View
from clams.appmetadata import AppMetadata, RuntimeParameter, real_valued_primitives

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
        RuntimeParameter(**{
            'name': 'pretty', 'type': 'boolean', 'choices': None, 'default': False, 'multivalued': False,
            'description': 'The JSON body of the HTTP response will be re-formatted with 2-space indentation',
        }),
    ]
    # this key is used to store users' raw input params in the parameter dict 
    # even after "refinement" (i.e., casting to proper data types)
    _RAW_PARAMS_KEY = "#RAW#"

    def __init__(self):
        self.metadata: AppMetadata = self._load_appmetadata()
        super().__init__()
        # data type specification for common parameters

        for param in ClamsApp.universal_parameters:
            self.metadata.parameters.append(param)
        self.metadata_param_caster = ParameterCaster(ClamsApp.universal_parameters)  # pytype: disable=wrong-arg-types
        self.annotate_param_caster = ParameterCaster(self.metadata.parameters)  # pytype: disable=wrong-arg-types
        self.logger = logging.getLogger(self.metadata.identifier)
        
    def appmetadata(self, **kwargs: List[str]) -> str:
        """
        A public method to get metadata for this app as a string.

        :return: Serialized JSON string of the metadata
        """
        # cast only, no refinement
        casted = self.metadata_param_caster.cast(kwargs)
        pretty = casted.pop('pretty') if 'pretty' in casted else False
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

    def annotate(self, mmif: Union[str, dict, Mmif], **runtime_params: List[str]) -> str:
        """
        A public method to invoke the primary app function. It's essentially a
        wrapper around :meth:`~clams.app.ClamsApp._annotate` method where some common operations
        (that are invoked by keyword arguments) are implemented.

        :param mmif: An input MMIF object to annotate
        :param runtime_params: An arbitrary set of k-v pairs to configure the app at runtime
        :return: Serialized JSON string of the output of the app
        """
        if not isinstance(mmif, Mmif):
            mmif = Mmif(mmif)
        issued_warnings = []
        for key in runtime_params:
            if key not in self.annotate_param_caster.param_spec:
                issued_warnings.append(UserWarning(f'An undefined parameter "{key}" (value: "{runtime_params[key]}") is passed'))
        # this will do casting + refinement altogether
        refined = self._refine_params(**runtime_params)
        pretty = refined.get('pretty', False)
        with warnings.catch_warnings(record=True) as ws:
            annotated = self._annotate(mmif, **refined)
            if ws:
                issued_warnings.extend(ws)
        if issued_warnings:
            warnings_view = annotated.new_view()
            self.sign_view(warnings_view, runtime_params)
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
        #. Call :meth:`~mmif.serialize.view.View.new_contain` on the new view object with any annotation properties specified by the configuration.
        #. Process the data and create :class:`~mmif.serialize.annotation.Annotation` objects and add them to the new view. 
        #. While doing so, get help from :class:`~mmif.vocabulary.document_types.DocumentTypes`, :class:`~mmif.vocabulary.annotation_types.AnnotationTypes` classes to generate ``@type`` strings.
        #. Return the mmif object

        :param mmif: An input MMIF object to annotate
        :param runtime_params: An arbitrary set of k-v pairs to configure the app at runtime
        :return: A :class:`~mmif.serialize.mmif.Mmif` object of the annotated output, ready for serialization
        """
        raise NotImplementedError()
    
    def _refine_params(self, **runtime_params: List[str]):
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
        refined = {}
        
        casted = self.annotate_param_caster.cast(runtime_params)
        for parameter in self.metadata.parameters:
            if parameter.name in casted:
                if parameter.choices and casted[parameter.name] not in parameter.choices:
                    raise ValueError(f"Value for parameter \"{parameter.name}\" must be one of {parameter.choices}.")
                refined[parameter.name] = casted[parameter.name]
            elif parameter.default is not None:
                refined[parameter.name] = parameter.default
            else:
                raise ValueError(f"Cannot find configuration for a required parameter \"{parameter.name}\".")
        # raw input params are hidden under a special key
        refined[self._RAW_PARAMS_KEY] = runtime_params
        return refined
    
    def get_configuration(self, **runtime_params):
        warnings.warn("ClamsApp.get_configuration() is deprecated. "
                      "If you are using this method in `_annotate()` method,"
                      "it is no longer needed since `clams-python>1.0.9`.", 
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
                          "no longer be optional in the future. Please pass `runtime_params` "
                          "from _annotate() method.",
                          FutureWarning, stacklevel=2)
            return
        view.metadata.app = self.metadata.identifier
        if self._RAW_PARAMS_KEY in runtime_conf:
            for k, v in runtime_conf.items():
                if k == self._RAW_PARAMS_KEY:
                    for orik, oriv in v.items():
                        if orik in self.metadata.parameters and self.metadata.parameters[orik].multivalued:
                            view.metadata.add_parameter(orik, str(oriv))
                        else:
                            view.metadata.add_parameter(orik, oriv[0])
                view.metadata.add_app_configuration(k, v)
        else:
            # meaning the parameters directly from flask or argparser and values are in lists
            for k, v in runtime_conf.items():
                if k in self.metadata.parameters and self.metadata.parameters[k].multivalued:
                    view.metadata.add_parameter(k, str(v))
                else:
                    view.metadata.add_parameter(k, v[0])
        
    def set_error_view(self, mmif: Union[str, dict, Mmif], **runtime_conf: List[str]) -> Mmif:
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


class ParameterCaster(object):
    KV_DELIMITER = ':'
    python_type = {"boolean": bool, "number": float, "integer": int, "string": str, "map": dict}

    """
    A helper class to convert parameters passed by HTTP query strings to
    proper python data types.

    :param param_spec: A specification of a data types of parameters
    """
    def __init__(self, params: Iterable[RuntimeParameter]):
        self.param_spec = {}
        for param in params:
            self.param_spec[param.name] = (self.python_type[param.type], param.multivalued)

    def cast(self, args: Dict[str, List[str]]) \
            -> Dict[str, Union[real_valued_primitives, List[real_valued_primitives], Dict[str, str]]]:
        """
        Given parameter specification, tries to cast values of args to specified Python data types.
        Note that this caster deals with query strings, thus all keys and values in the input args are plain strings. 
        Also note that the caster does not handle "unexpected" parameters came as an input. 
        Handling (raising an exception or issuing a warning upon receiving) an unexpected runtime parameter 
        must be done within the app itself.
        Thus, when a key is not found in the parameter specifications, it should just pass it as a vanilla string.

        :param args: k-v pairs
        :return: A new dictionary of type-casted args, of which keys are always strings (parameter name), 
                 and values are either 
                 1) a single value of a specified type (multivalued=False)
                 2) a list of values of a specified type (multivalued=True) (all duplicates in the input are kept)
                 3) a nested string-string dictionary (type=map ⊨ multivalued=True)
                 With the third case, developers can further process the nested values into a more complex data types or
                 structures, but that is not in the scope of this Caster class. 
        """
        casted = {}
        for k, vs in args.items():
            assert isinstance(vs, list), f"Expected a list of values for key {k}, but got {vs} of type {type(vs)}"
            assert all(isinstance(v, str) for v in vs), f"Expected a list of strings for key {k}, but got {vs} of types {[type(v) for v in vs]}"
            if k in self.param_spec:
                for v in vs:
                    valuetype, multivalued = self.param_spec[k]
                    if multivalued or k not in casted:  # effectively only keeps the first value for non-multi params
                        if valuetype == bool:
                            v = self.bool_param(v)
                        elif valuetype == float:
                            v = self.float_param(v)
                        elif valuetype == int:
                            v = self.int_param(v)
                        elif valuetype == str:
                            v = self.str_param(v)
                        elif valuetype == dict:
                            v = self.kv_param(v)
                        if multivalued:
                            if valuetype == dict:
                                casted.setdefault(k, {}).update(v)
                            else:
                                casted.setdefault(k, []).append(v)
                        else: 
                            casted[k] = v
            else:
                if len(vs) > 1:
                    casted[k] = vs
                else:
                    casted[k] = vs[0]
        return casted  # pytype: disable=bad-return-type

    @staticmethod
    def bool_param(value) -> bool:
        """
        Helper function to convert string values to bool type.
        """
        return False if value in (False, 0, 'False', 'false', '0') else True

    @staticmethod
    def float_param(value) -> float:
        """
        Helper function to convert string values to float type.
        """
        return float(value)

    @staticmethod
    def int_param(value) -> int:
        """
        Helper function to convert string values to int type.
        """
        return int(value)

    @staticmethod
    def str_param(value) -> str:
        """
        Helper function to convert string values to string type.
        """
        return value
    
    @staticmethod
    def kv_param(value) -> Dict[str, str]:
        """
        Helper function to convert string values to key-value pair type.
        """
        return dict([value.split(ParameterCaster.KV_DELIMITER, 1)])
