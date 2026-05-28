import json
import logging
import os
import pathlib
import sys
import warnings
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from urllib import parse as urlparser

__all__ = ['ClamsApp', 'ClamsPromptableApp', 'ClamsHFPromptableApp']

from typing import Union, Any, Optional, Dict, List, Tuple, cast

from mmif import Mmif, Document, DocumentTypes, View, AnnotationTypes
from mmif.utils.video_document_helper import (
    SamplingMode, SAMPLING_MODE_DESCRIPTIONS, SAMPLING_MODE_DEFAULT,
    _sampling_mode,
)
from mmif.utils.workflow_helper import generate_param_hash  # pytype: disable=import-error
from clams.appmetadata import AppMetadata, real_valued_primitives, python_type, map_param_kv_delimiter
from clams.envelop import unwrap_if_envelope

logging.basicConfig(
    level=getattr(logging, os.environ.get('CLAMS_LOGLEVEL', 'WARNING').upper(), logging.WARNING),
    format="%(asctime)s %(name)s %(levelname)-8s %(thread)d %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")


_sampling_mode_choices = [m.value for m in SamplingMode]
_sampling_mode_description = (
    'Sampling mode for TimeFrame annotations. '
    'Has no effect when the app does not process TimeFrames. '
    + ' '.join(
        f'"{m.value}" {SAMPLING_MODE_DESCRIPTIONS[m]}'
        for m in SamplingMode
    )
)

falsy_values = [
    'False', 
    'false', 
    'F',
    'f',
    '0',
    0, 
    False
]


class ClamsApp(ABC):
    """
    An abstract class to define API's for ClamsApps. A CLAMS app should inherit
    this class and then can be used with classes in :mod:`.restify` to work as
    web applications.
    """
    # A set of "universal runtime parameters that can be used for both GET and POST anytime".
    # The behavioral changes based on these parameters must be implemented on the SDK level. 
    # This needs to stay as a list of dicts for compatibility with the metadata.py file (templated).
    universal_parameters = [
        {
            'name': 'pretty', 'type': 'boolean', 'choices': None, 'default': False, 'multivalued': False,
            'description': 'The JSON body of the HTTP response will be re-formatted with 2-space indentation',
        },
        {
            'name': 'runningTime', 'type': 'boolean', 'choices': None, 'default': True, 'multivalued': False,
            'description': 'The running time of the app will be recorded in the view metadata',
        },
        {
            'name': 'hwFetch', 'type': 'boolean', 'choices': None, 'default': False, 'multivalued': False,
            'description': 'The hardware information (architecture, GPU and vRAM) will be recorded in the view metadata',
        },
        # tfSamplingMode is universal (not per-app) because it controls
        # how vdh.extract_frames_by_mode() selects frames from TimeFrames.
        # The value is intercepted in annotate() and pushed into a
        # contextvars.ContextVar so that any vdh call inside _annotate()
        # picks it up automatically — app developers never need to handle
        # this parameter themselves.
        {
            'name': 'tfSamplingMode', 'type': 'string',
            'choices': _sampling_mode_choices,
            'default': SAMPLING_MODE_DEFAULT.value,
            'multivalued': False,
            'description': _sampling_mode_description,
        },
    ]
    
    # this key is used to store users' raw input params in the parameter dict 
    # even after "refinement" (i.e., casting to proper data types)
    _RAW_PARAMS_KEY = "#RAW#"

    def __init__(self):
        self.metadata: AppMetadata = self._load_appmetadata()
        super().__init__()
        
        # data type spec to be used in type caster
        self.metadata_param_spec = {}
        self.annotate_param_spec = {}
        for param in ClamsApp.universal_parameters:
            # in addition to building the param spec, add them as regular params, so they are serialized in metadata
            self.metadata.add_parameter(**param)  
            self.metadata_param_spec[param['name']] = (param['type'], param.get('multivalued', False))
        for param_spec in self.metadata.parameters:
            self.annotate_param_spec[param_spec.name] = (param_spec.type, param_spec.multivalued)

        self.metadata_param_caster = ParameterCaster(self.metadata_param_spec)
        self.annotate_param_caster = ParameterCaster(self.annotate_param_spec)
        self.logger = logging.getLogger(str(self.metadata.identifier))
        
    def appmetadata(self, **kwargs: List[str]) -> str:
        """
        A public method to get metadata for this app as a string.

        :return: Serialized JSON string of the metadata
        """
        # cast only, no refinement
        casted = self.metadata_param_caster.cast(kwargs)
        pretty = casted.get('pretty', False)
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
        see `https://clams.ai/clams-python/appmetadata.jsonschema <../appmetadata.jsonschema>`_. 
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

        The input may be a raw MMIF (str, dict, or :class:`~mmif.serialize.mmif.Mmif`)
        or a JSON envelope wrapping both ``"parameters"`` and ``"mmif"``.
        Envelope detection and unwrapping happen here so every execution
        path (HTTP, CLI, direct Python API) is envelope-aware. When an
        envelope is given, its parameters are merged under ``runtime_params``
        (explicitly-passed parameters take priority on key collision).

        :param mmif: An input MMIF object, or a JSON envelope, to annotate
        :param runtime_params: An arbitrary set of k-v pairs to configure the app at runtime
        :return: Serialized JSON string of the output of the app
        """
        if not isinstance(mmif, Mmif):
            mmif, runtime_params = unwrap_if_envelope(mmif, runtime_params)
            mmif = Mmif(mmif)
        existing_view_ids = {view.id for view in mmif.views}
        issued_warnings = []
        for key in runtime_params:
            if key not in self.annotate_param_spec:
                issued_warnings.append(UserWarning(f'An undefined parameter "{key}" (value: "{runtime_params[key]}") is passed'))
        # this will do casting + refinement altogether
        self.logger.debug(f"User parameters: {runtime_params}")
        refined = self._refine_params(**runtime_params)
        self.logger.debug(f"Refined parameters: {refined}")
        pretty = refined.get('pretty', False)
        sampling_mode_str = refined.get('tfSamplingMode', None)
        if sampling_mode_str is not None:
            _sampling_mode.set(SamplingMode(sampling_mode_str))
        t = datetime.now()
        with warnings.catch_warnings(record=True) as ws:
            annotated, cuda_profiler = self._profile_cuda_memory(self._annotate)(mmif, **refined)
            if ws:
                issued_warnings.extend(ws)
        if issued_warnings:
            warnings_view = annotated.new_view()
            self.sign_view(warnings_view, refined)
            warnings_view.metadata.warnings = issued_warnings
        run_id = datetime.now()
        td = run_id - t
        runningTime = refined.get('runningTime', False)
        hwFetch = refined.get('hwFetch', False)
        runtime_recs = {}
        if hwFetch:
            import multiprocessing
            import platform, shutil, subprocess
            runtime_recs['cpu'] = f"{platform.machine()}, {multiprocessing.cpu_count()} cores"
            runtime_recs['cuda'] = []
            # Use cuda_profiler data if available, otherwise fallback to nvidia-smi
            if cuda_profiler:
                for gpu_name, mem_info in cuda_profiler.items():
                    total_str = self._cuda_memory_to_str(mem_info['total'])
                    available_str = self._cuda_memory_to_str(mem_info['available_before'])
                    peak_str = self._cuda_memory_to_str(mem_info['peak'])
                    runtime_recs['cuda'].append(
                        f"{gpu_name}, {total_str} total, {available_str} available, {peak_str} peak used"
                    )
            elif shutil.which('nvidia-smi'):
                for gpu in subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], 
                                          stdout=subprocess.PIPE).stdout.decode('utf-8').strip().split('\n'):
                    name, mem = gpu.split(', ')
                    runtime_recs['cuda'].append(self._cuda_device_name_concat(name, mem))
        for annotated_view in annotated.views:
            if annotated_view.id not in existing_view_ids and annotated_view.metadata.app == str(self.metadata.identifier):
                annotated_view.metadata.timestamp = run_id
                profiling_data = {}
                if runningTime:
                    profiling_data['runningTime'] = str(td)
                if len(runtime_recs) > 0:
                    profiling_data['hardware'] = runtime_recs
                if profiling_data:
                    annotated_view.metadata.set_additional_property('appProfiling', profiling_data)
                    
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
                # have to cast the default values as well, since 
                # 1. `map` type default values are not actually expected as a map (dict)
                # 2. developers can use data type not matching the spec
                if isinstance(parameter.default, list):
                    casted_default = self.annotate_param_caster.cast({parameter.name: list(map(str, parameter.default))})
                else:
                    casted_default = self.annotate_param_caster.cast({parameter.name: [str(parameter.default)]})
                refined.update(casted_default)
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

    def sign_view(self, view: View, runtime_conf: dict) -> None:
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
        view.metadata.app = str(self.metadata.identifier)
        params_map = {p.name: p for p in self.metadata.parameters}
        if self._RAW_PARAMS_KEY in runtime_conf:
            for k, v in runtime_conf.items():
                if k == self._RAW_PARAMS_KEY:
                    for orik, oriv in v.items():
                        if orik in params_map and params_map[orik].multivalued:
                            view.metadata.add_parameter(orik, str(oriv))
                        else:
                            view.metadata.add_parameter(orik, oriv[0])
                else:
                    view.metadata.add_app_configuration(k, v)
        else:
            # meaning the parameters directly from flask or argparser and values are in lists
            for k, v in runtime_conf.items():
                if k in params_map and params_map[k].multivalued:
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
        if isinstance(mmif, (bytes, str, dict)):
            mmif, runtime_conf = unwrap_if_envelope(mmif, runtime_conf)
            mmif = Mmif(mmif)
        error_view: Optional[View] = None
        for view in reversed(mmif.views):
            if view.metadata.app == str(self.metadata.identifier):
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
    def _cuda_memory_to_str(mem) -> str:
        mib = mem / (1024 * 1024)
        return f"{mib:.0f} MiB"  # No decimal places

    @staticmethod
    def _cuda_device_name_concat(name, mem):
        if type(mem) in (bytes, int):
            mem = ClamsApp._cuda_memory_to_str(mem)
        return f"{name}, With {mem}"

    def _get_profile_path(self, param_hash: str) -> pathlib.Path:
        """
        Get filesystem path for memory profile file.

        Profile files are stored in a per-app directory under user's cache.

        :param param_hash: Hash of parameters from :func:`mmif.utils.cli.describe.generate_param_hash`
        :return: Path to the profile file
        """
        # Sanitize app identifier for filesystem use
        app_id = str(self.metadata.identifier).replace('/', '-').replace(':', '-')
        cache_base = pathlib.Path(os.environ.get('XDG_CACHE_HOME', pathlib.Path.home() / '.cache'))
        cache_dir = cache_base / 'clams' / 'memory_profiles' / app_id
        return cache_dir / f"memory_{param_hash}.json"

    @staticmethod
    def _get_available_vram() -> int:
        """
        Get currently available VRAM in bytes (GPU-wide, across all processes).

        Uses nvidia-smi to get actual available memory, not just current process.

        :return: Available VRAM in bytes, or 0 if unavailable
        """
        try:
            import subprocess
            import shutil
            if shutil.which('nvidia-smi'):
                # Get free memory from nvidia-smi (reports GPU-wide, not per-process)
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits', '-i', '0'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    free_mb = float(result.stdout.strip())
                    return int(free_mb * 1024 * 1024)  # Convert MB to bytes
        except Exception:
            pass

        # Fallback to torch (only sees current process memory)
        try:
            import torch  # pytype: disable=import-error
            if not torch.cuda.is_available():
                return 0

            device = torch.cuda.current_device()
            total = torch.cuda.get_device_properties(device).total_memory
            used = max(torch.cuda.memory_allocated(device),
                       torch.cuda.memory_reserved(device))
            return total - used
        except Exception:
            return 0

    def _record_vram_usage(self, parameters: dict, peak_bytes: int) -> None:
        """
        Record peak memory usage to profile file.

        Uses atomic write (temp + rename) to avoid corruption from
        concurrent writes. Only updates if new value is higher.

        Profile files are JSON containing:
        - peak_bytes: Peak VRAM usage by the torch process
        - parameters: Original parameters for human readability

        :param parameters: Request parameters (for hash and recording)
        :param peak_bytes: Measured peak VRAM usage
        """
        import json

        if peak_bytes <= 0:
            return

        param_hash = generate_param_hash(parameters)
        profile_path = self._get_profile_path(param_hash)

        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if we should update
            should_write = True
            if profile_path.exists():
                try:
                    existing_data = json.loads(profile_path.read_text())
                    existing = existing_data.get('peak_bytes', 0)
                    if peak_bytes <= existing:
                        should_write = False  # Existing value is sufficient
                    else:
                        self.logger.debug(
                            f"Updating peak memory for {param_hash}: "
                            f"{self._cuda_memory_to_str(existing)} -> {self._cuda_memory_to_str(peak_bytes)}"
                        )
                except (ValueError, IOError, json.JSONDecodeError):
                    pass  # Corrupted file, overwrite

            if should_write:
                # Prepare profile data with original parameters for readability
                # Filter out internal keys and non-serializable values
                clean_params = {
                    k: v for k, v in parameters.items()
                    if k != self._RAW_PARAMS_KEY and not k.startswith('#')
                }
                profile_data = {
                    'peak_bytes': peak_bytes,
                    'parameters': clean_params
                }

                # Atomic write: write to temp, then rename
                temp_path = profile_path.with_suffix('.tmp')
                temp_path.write_text(json.dumps(profile_data, indent=2))
                temp_path.rename(profile_path)  # Atomic on POSIX

                self.logger.info(
                    f"Recorded peak memory for {param_hash}: "
                    f"{self._cuda_memory_to_str(peak_bytes)}"
                )
        except Exception as e:
            self.logger.warning(f"Failed to record memory profile: {e}")

    @staticmethod
    def _profile_cuda_memory(func):
        """
        Decorator for profiling CUDA memory usage and managing VRAM availability.

        This decorator:
        1. Checks VRAM requirements before execution (if conditions met)
        2. Rejects requests if insufficient VRAM
        3. Records peak memory usage after execution
        4. Calls empty_cache() for cleanup

        :param func: The function to wrap (typically _annotate)
        :return: Decorated function that returns (result, cuda_profiler)
                 where cuda_profiler is dict with "<GPU_NAME>, <GPU_TOTAL_MEMORY>" keys
                 and dict values containing 'available_before' and 'peak' memory in bytes
        """
        def wrapper(*args, **kwargs):
            # Get the ClamsApp instance from the bound method
            app_instance = getattr(func, '__self__', None)

            cuda_profiler = {}
            torch_available = False
            cuda_available = False
            device_count = 0
            available_before = {}

            try:
                import torch  # pytype: disable=import-error
                torch_available = True
                cuda_available = torch.cuda.is_available()
                device_count = torch.cuda.device_count()
            except ImportError:
                pass

            # Capture available VRAM before execution and reset stats
            if torch_available and cuda_available:
                for device_id in range(device_count):
                    device_id_str = f'cuda:{device_id}'
                    # Get GPU-wide available memory via nvidia-smi
                    try:
                        import subprocess
                        import shutil
                        if shutil.which('nvidia-smi'):
                            result = subprocess.run(
                                ['nvidia-smi', '--query-gpu=memory.free',
                                 '--format=csv,noheader,nounits', '-i', str(device_id)],
                                capture_output=True, text=True, timeout=5
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                free_mb = float(result.stdout.strip())
                                available_before[device_id] = int(free_mb * 1024 * 1024)
                            else:
                                # Fallback to torch (process-specific)
                                total = torch.cuda.get_device_properties(device_id_str).total_memory
                                allocated = torch.cuda.memory_allocated(device_id_str)
                                available_before[device_id] = total - allocated
                        else:
                            # Fallback to torch (process-specific)
                            total = torch.cuda.get_device_properties(device_id_str).total_memory
                            allocated = torch.cuda.memory_allocated(device_id_str)
                            available_before[device_id] = total - allocated
                    except Exception:
                        # Fallback to torch (process-specific)
                        total = torch.cuda.get_device_properties(device_id_str).total_memory
                        allocated = torch.cuda.memory_allocated(device_id_str)
                        available_before[device_id] = total - allocated
                # Reset peak memory stats for all devices
                torch.cuda.reset_peak_memory_stats('cuda')

            try:
                result = func(*args, **kwargs)

                # Record peak memory usage
                total_peak = 0
                if torch_available and cuda_available and device_count > 0:
                    for device_id in range(device_count):
                        device_id_str = f'cuda:{device_id}'
                        peak_memory = torch.cuda.max_memory_allocated(device_id_str)
                        total_peak = max(total_peak, peak_memory)
                        gpu_name = torch.cuda.get_device_name(device_id_str)
                        gpu_total_memory = torch.cuda.get_device_properties(device_id_str).total_memory
                        cuda_profiler[gpu_name] = {
                            'total': gpu_total_memory,
                            'available_before': available_before.get(device_id, 0),
                            'peak': peak_memory
                        }

                    # Record peak memory for future requests (if GPU app)
                    gpu_app = (
                        hasattr(app_instance, 'metadata') and
                        getattr(app_instance.metadata, 'est_gpu_mem_min', 0) > 0
                    )
                    if gpu_app and total_peak > 0:
                        app_instance._record_vram_usage(kwargs, total_peak)

                return result, cuda_profiler
            finally:
                if torch_available and cuda_available:
                    torch.cuda.empty_cache()

        return wrapper

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


# TODO (krim @ 05/28/26): maybe we should consider implementing
# autodoc-based auto documentation export (e.g., ``automethod`` for
# methods and a small Sphinx extension to render
# ``promptable_parameters`` into the parameter table), instead of the
# current hand-authored ``documentation/app-baseclasses.rst``. 
class ClamsPromptableApp(ClamsApp):
    """
    Base class for CLAMS apps that wrap a promptable model (an LLM or
    other multimodal model, local or remote). Standardizes the runtime
    parameter surface
    (prompt, generation hyperparameters, batch size) and provides
    helpers for building chat conversations and persisting model
    responses into MMIF.

    The standardized parameters are listed in
    :py:attr:`promptable_parameters` and added to an app's metadata via
    :py:meth:`inject_promptable_parameters`. Promptable-app developers
    MUST call that helper at the end of their ``appmetadata()`` function
    in ``metadata.py``. The reservation rule (these parameter names are
    SDK-managed and apps cannot redeclare them) is enforced implicitly
    via :py:meth:`AppMetadata.add_parameter`'s existing duplicate-name
    check.

    Inference is performed by :py:meth:`generate`, which subclasses MUST
    implement. The base class provides:

    * :py:meth:`inject_promptable_parameters` — add the SDK-managed
      parameter set to ``AppMetadata``
    * :py:meth:`build_conversation` — assemble a chat-template-compatible
      message list (stub in this release)
    * :py:meth:`response_to_grounded_textdocument` — persist a
      generated response into a view as ``TextDocument`` +
      ``Alignment`` (+ optional ``origins`` / ``origination``)
    """

    #: SDK-managed runtime parameters injected into every promptable app.
    #: These names are reserved — apps cannot redeclare them with
    #: customized specs.
    promptable_parameters = [
        {
            'name': 'prompt', 'type': 'string', 'multivalued': True,
            'description':
                'User prompt(s) sent to the model. A single value runs as a '
                'one-shot generation. A multi-value list is interpreted as a '
                'multi-turn static prompt; see ``promptMode`` for how turns '
                'are assembled.',
        },
        {
            'name': 'systemPrompt', 'type': 'string', 'default': '',
            'description':
                'Optional system-role text prepended to the conversation. '
                'Empty by default.',
        },
        {
            'name': 'promptMode', 'type': 'string',
            'choices': ['user-only', 'turn-taking'],
            'default': 'turn-taking',
            'description':
                'How to interpret a multi-value ``prompt`` list. '
                'Has no effect when ``prompt`` has a single value. '
                'For semantics of each choice and worked examples, see '
                'https://clams.ai/clams-python/app-baseclasses.html#promptable-multiturn',
        },
        {
            'name': 'maxNewTokens', 'type': 'integer', 'default': 512,
            'description':
                'Maximum number of new tokens generated per inference call. '
                'Forwarded to the backend\'s ``generate``-equivalent. Larger '
                'values grow the KV cache linearly and increase GPU memory '
                'usage; reduce if VRAM is constrained.',
        },
        {
            'name': 'temperature', 'type': 'number', 'default': 0.0,
            'description':
                'Sampling temperature. The default ``0.0`` selects '
                'deterministic / greedy decoding for maximum reproducibility; '
                'override for sampled generation.',
        },
        {
            'name': 'topP', 'type': 'number', 'default': 1.0,
            'description':
                'Nucleus-sampling cumulative probability cutoff. Only '
                'meaningful when ``temperature`` is greater than 0.',
        },
        {
            'name': 'topK', 'type': 'integer', 'default': 50,
            'description':
                'Top-K sampling cutoff. Only meaningful when ``temperature`` '
                'is greater than 0.',
        },
        {
            'name': 'parallelPrompts', 'type': 'integer', 'default': 1,
            'description':
                'Number of independent prompts the app runs in parallel '
                '(stacks into a single forward pass). The *size* of each '
                'prompt (how many images, how long the system/user text '
                'is, etc.) is NOT regulated by this parameter; that is '
                'each app\'s responsibility. Prompt count and per-prompt '
                'content size combine multiplicatively for GPU memory, '
                'so the two can blow up together. Catastrophic example: '
                '``tfSamplingMode=all`` on a TimeFrame without '
                '``targets`` expands that TF into one image per '
                'native-FPS frame (300 images for a 10-second TF at '
                '30fps); ``parallelPrompts=4`` then runs 4 such prompts '
                'in one forward pass (~1200 images), guaranteed OOM. '
                'Keep at ``1`` on memory-tight setups; raise only when '
                'per-prompt content is small and bounded.',
        },
    ]

    @staticmethod
    def inject_promptable_parameters(metadata: AppMetadata) -> None:
        """
        Add the SDK-managed promptable parameters to ``metadata``. Call
        this at the end of your app's ``appmetadata()`` function in
        ``metadata.py`` if your app subclasses
        :py:class:`ClamsPromptableApp`.

        The reservation rule is enforced implicitly: if the app had
        already called ``metadata.add_parameter('prompt', ...)`` (or
        any other promptable name) before this helper, the helper's own
        ``add_parameter`` call will trip the existing duplicate-name
        ``ValueError`` in :py:meth:`AppMetadata.add_parameter`.

        :param metadata: the :class:`AppMetadata` instance being built
        """
        for param in ClamsPromptableApp.promptable_parameters:
            metadata.add_parameter(**param)

    def __init__(self):
        # ``ClamsApp.__init__`` loads the app's ``metadata.py``, which
        # is expected to have already called
        # ``inject_promptable_parameters()`` from inside
        # ``appmetadata()``. The parent ``__init__`` then iterates
        # ``self.metadata.parameters`` to populate
        # ``annotate_param_spec`` and build the caster — so the
        # promptable parameters are already covered by the time we land
        # here. We only validate that the helper was actually called.
        super().__init__()
        declared = {p.name for p in self.metadata.parameters}
        expected = {p['name'] for p in ClamsPromptableApp.promptable_parameters}
        missing = expected - declared
        if missing:
            raise ValueError(
                f"Promptable parameters {sorted(missing)} are missing "
                f"from the app metadata. Promptable apps must call "
                f"``ClamsPromptableApp.inject_promptable_parameters("
                f"metadata)`` inside their ``appmetadata()`` function "
                f"in ``metadata.py``."
            )

    @abstractmethod
    def generate(
            self,
            prompt: List[str],
            system_prompt: str = '',
            images: Optional[List[List[Any]]] = None,
            audios: Optional[List[List[Any]]] = None,
            prompt_mode: str = 'turn-taking',
            **generation_params,
    ) -> List[str]:
        """
        Run N independent prompts in one inference call and return N
        outputs. Subclasses MUST implement this.

        Each inner list of ``images`` / ``audios`` is the bundled
        multimodal content for ONE prompt -- the model sees those
        items as one composite input and produces one output. The
        outer list spans N prompts processed in parallel (when the
        backend supports it; sequentially otherwise).

        * Single-prompt call: ``images=[[img1, img2]]`` -> one output
          (composite over the two bundled images).
        * Per-input broadcast: ``images=[[img1], [img2], [img3]]`` ->
          three outputs (one per image). Caller assembles the
          singleton-wrap shape.
        * Multimodal pair: ``images=[[img1]], audios=[[au1]]`` -> one
          output. When both ``images`` and ``audios`` are given they
          must have the same outer length; index ``i`` of each pairs
          into prompt ``i``.

        :param prompt: a ``List[str]`` of prompt turns. A
            single-element list is one-shot. A multi-element list is
            multi-turn and is assembled according to ``prompt_mode``.
        :param system_prompt: optional system-role text prepended to
            the conversation. Applies to every prompt in the batch.
        :param images: optional ``List[List[Any]]`` -- N groups, one
            per prompt; each inner list is the bundled images for that
            prompt.
        :param audios: optional ``List[List[Any]]`` -- N groups, one
            per prompt; each inner list is the bundled audio clips
            for that prompt.
        :param prompt_mode: ``"turn-taking"`` (default) or
            ``"user-only"``; see :py:attr:`promptable_parameters`.
        :param generation_params: any additional backend-specific
            generation kwargs (``maxNewTokens``, ``temperature``,
            ``topP``, ``topK``, etc.).
        :return: a ``List[str]`` with one entry per prompt in the
            batch. For ``prompt_mode='user-only'`` multi-turn, each
            prompt's entry is the assistant's final reply across its
            N user turns.
        :rtype: List[str]
        """
        raise NotImplementedError

    def build_conversation(
            self,
            prompt: Union[str, List[str], List[dict]],
            system_prompt: str = '',
            images: Optional[List[Any]] = None,
            audios: Optional[List[Any]] = None,
            prompt_mode: str = 'turn-taking',
    ) -> Union[List[dict], List[List[dict]]]:
        """
        Build a chat-template-compatible message list.

        :param prompt: a plain string, a ``List[str]`` of prompt turns,
            or a pre-built ``List[dict]`` of role/content message
            objects (returned as-is — pass-through for advanced
            callers that constructed the conversation themselves).
        :param system_prompt: if non-empty, prepended as a
            system-role message.
        :param images: optional list of image inputs to include in the
            (final) user turn's content. Each appears as a
            ``{'type': 'image', 'image': <input>}`` entry.
        :param audios: optional list of audio inputs to include in the
            (final) user turn's content. Each appears as a
            ``{'type': 'audio', 'audio': <input>}`` entry.
        :param prompt_mode: ``"turn-taking"`` (default) or
            ``"user-only"``. Only meaningful when ``prompt`` is a
            multi-element list; ignored otherwise. See
            :py:attr:`promptable_parameters` for semantics.

        :returns:
            * For single-shot prompts (string or single-element list)
              and for multi-element ``turn-taking`` mode: a single
              ``List[dict]`` of role/content messages, ready to feed
              to a chat-template applier (e.g.,
              ``processor.apply_chat_template``).
            * For multi-element ``user-only`` mode: a
              ``List[List[dict]]`` of N progressively-extending
              conversation prefixes, one per user turn. Each prefix
              ends in a user turn; assistant turns between users are
              stored with ``content=None`` as placeholders for the
              caller to fill in with successive generation results.

        Subclasses may override to access model-specific state
        (``self.processor``, ``self.tokenizer``, etc.) during
        formatting; the base implementation is back-end-agnostic.
        """
        # Pass-through for pre-built message lists.
        if isinstance(prompt, list) and prompt and all(
                isinstance(p, dict) for p in prompt):
            return cast(List[dict], prompt)

        # Normalize to List[str].
        if isinstance(prompt, str):
            prompts = [prompt]
        else:
            prompts = list(prompt)

        if len(prompts) == 1:
            return self._build_single_turn(
                prompts[0], system_prompt, images, audios)

        if prompt_mode == 'turn-taking':
            return self._build_turn_taking(
                prompts, system_prompt, images, audios)
        if prompt_mode == 'user-only':
            return self._build_user_only(
                prompts, system_prompt, images, audios)
        raise ValueError(
            f"Unknown prompt_mode: {prompt_mode!r}. "
            f"Expected 'turn-taking' or 'user-only'.")

    @staticmethod
    def _make_user_content(text, images=None, audios=None):
        """Build the content list for a user-role message."""
        content = []
        if images:
            for img in images:
                content.append({'type': 'image', 'image': img})
        if audios:
            for au in audios:
                content.append({'type': 'audio', 'audio': au})
        content.append({'type': 'text', 'text': text})
        return content

    def _build_single_turn(self, text, system_prompt, images, audios):
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({
            'role': 'user',
            'content': self._make_user_content(text, images, audios),
        })
        return messages

    def _build_turn_taking(self, prompts, system_prompt, images, audios):
        """
        Alternating user/assistant turns; one inference call.
        Even indices in ``prompts`` are user turns, odd indices are
        pre-written assistant exemplars. Images/audios (if any) are
        attached to the final user turn (the actual query).
        """
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        # index of the final user turn (the last even index)
        last_user_idx = (len(prompts) - 1) - ((len(prompts) - 1) % 2)
        for i, text in enumerate(prompts):
            role = 'user' if i % 2 == 0 else 'assistant'
            if role == 'user':
                attach_media = (i == last_user_idx)
                content = self._make_user_content(
                    text,
                    images if attach_media else None,
                    audios if attach_media else None,
                )
                messages.append({'role': 'user', 'content': content})
            else:
                messages.append({'role': 'assistant', 'content': text})
        return messages

    def _build_user_only(self, prompts, system_prompt, images, audios):
        """
        N progressively-extending conversation prefixes, one per user
        turn. Assistant slots between users have ``content=None`` as
        placeholders for the caller's successive generation results.
        """
        convs: List[List[dict]] = []
        base: List[dict] = []
        if system_prompt:
            base.append({'role': 'system', 'content': system_prompt})
        for i, text in enumerate(prompts):
            # First user turn carries the images/audios (the initial query);
            # subsequent user turns are text-only.
            user_content = self._make_user_content(
                text,
                images if i == 0 else None,
                audios if i == 0 else None,
            )
            base.append({'role': 'user', 'content': user_content})
            # Snapshot the conversation as it stands at the start of
            # the i-th generation call. Shallow-copy each message so
            # later in-place edits (e.g., filling in the assistant
            # placeholder) don't retroactively mutate earlier
            # snapshots.
            convs.append([dict(m) for m in base])
            if i < len(prompts) - 1:
                base.append({'role': 'assistant', 'content': None})
        return convs

    def response_to_grounded_textdocument(
            self,
            view: View,
            source: str,
            response: str,
            origins: Optional[List[str]] = None,
            origination: Optional[str] = None,
            reasoning_trace: Optional[str] = None,
    ) -> Tuple[Any, Any]:
        """
        Persist a single LLM text response into a view. Writes one
        ``TextDocument`` (containing the response) plus possible
        grounding via an ``Alignment`` annotation and ``origins`` / 
        ``origination`` properties on the TD.

        The two grounding link kinds are semantically distinct:

        * ``source`` is the *coarse* cross-modal grounding -- the
          single annotation id that the response is anchored to.
          Written into the new ``Alignment`` (``source -> td``).
          Typical value: the parent ``TimeFrame`` for a
          captioning/OCR app.
        * ``origins`` are the *finer* derivation grounding -- a list
          of annotation ids the response was specifically derived
          from (e.g. the ``TimePoint``\\s whose frames were fed to
          the model). Written into ``TextDocument.origins``. See
          https://clams.ai/clams-vocabulary/Document for vocabulary
          semantics.

        :param view: the :class:`View` to write into. The caller is
            responsible for having called
            :meth:`View.new_contain` for ``TextDocument`` and
            ``Alignment`` first if needed.
        :param source: ``id`` of the annotation to record as the
            cross-modal anchor of the response (see above).
        :param response: the text generated by the model.
        :param origins: optional list of ``id``\\s of annotations the
            response was *derived* from. Must be paired with
            ``origination``.
        :param origination: nature of the derivation, written to
            ``TextDocument.origination``. Accepted values per the
            vocabulary include ``'derived'``, ``'transcription'``,
            ``'topologically-identical'``. Must be paired with
            ``origins``.
        :param reasoning_trace: optional model-side reasoning trace
            (a chain-of-thought / scratchpad string, NOT a Python
            traceback). NOT YET SUPPORTED -- passing a non-``None``
            value raises :py:class:`NotImplementedError`. Storage
            convention is still being decided at
            clamsproject/clams-python#263.
        :return: ``(TextDocument, Alignment)`` tuple of the new
            annotations.
        :raises ValueError: if exactly one of ``origins`` /
            ``origination`` is set; they must be supplied together
            or both omitted.
        """
        if bool(origins) != bool(origination):
            raise ValueError(
                "`origins` and `origination` must be supplied together "
                "or both omitted; got "
                f"origins={origins!r}, origination={origination!r}."
            )
        td = view.new_textdocument(text=response)
        if origins:
            td.add_property('origins', origins)
            td.add_property('origination', origination)
        align = view.new_annotation(
            AnnotationTypes.Alignment,
            source=source,
            target=td.id,
        )
        if reasoning_trace is not None:
            raise NotImplementedError(
                "Reasoning-trace storage convention is not yet defined; "
                "tracked at clamsproject/clams-python#263."
            )
        return td, align


class ClamsHFPromptableApp(ClamsPromptableApp):
    """
    Base class for promptable CLAMS apps backed by a local
    HuggingFace ``transformers`` model. Layers HF-specific inference
    plumbing on top of :class:`ClamsPromptableApp`: model loading
    via :func:`clams.backends.hf.load_hf_model`, and a concrete
    :py:meth:`generate` implementation that runs N independent
    prompts in one HF forward pass via the standard
    chat-template -> ``model.generate`` -> ``batch_decode`` pipeline.

    Concrete subclasses declare the model via class attributes
    (:py:attr:`MODEL_ID`, :py:attr:`MODEL_CLS`, etc.) and typically
    only need to implement :py:meth:`_annotate` -- the per-app MMIF
    I/O. Example::

        class MyVLMCaptioner(ClamsHFPromptableApp):
            MODEL_ID = "HuggingFaceTB/SmolVLM2-2.2B-Instruct"
            MODEL_CLS = AutoModelForImageTextToText
            DTYPE = torch.bfloat16
            PADDING_SIDE = 'left'

            def _annotate(self, mmif, **parameters):
                # collect tasks from MMIF, build image groups, then
                #   texts = self.generate(prompt, images=image_groups, ...)
                # store responses via self.response_to_grounded_textdocument
                ...

    Requires the ``[hf]`` extra (``pip install clams-python[hf]``).
    """

    #: HuggingFace model identifier (Hub repo name or local path).
    #: Subclasses MUST set this.
    MODEL_ID: Optional[str] = None
    #: ``transformers`` model class (e.g.
    #: :class:`~transformers.AutoModelForImageTextToText`,
    #: :class:`~transformers.AutoModelForCausalLM`). Subclasses MUST
    #: set this.
    MODEL_CLS: Optional[Any] = None
    #: ``transformers`` processor / tokenizer / feature-extractor
    #: class. Defaults to :class:`~transformers.AutoProcessor` (set
    #: by :func:`clams.backends.hf.load_hf_model` when ``None``).
    PROCESSOR_CLS: Optional[Any] = None
    #: Torch dtype for the model (e.g. ``torch.bfloat16``). When
    #: ``None``, the model class's own default is used (typically
    #: float32). Also used to cast ``pixel_values`` in
    #: :py:meth:`generate`.
    DTYPE: Optional[Any] = None
    #: Tokenizer padding side. Set to ``'left'`` for decoder-only
    #: batched generation; leave ``None`` otherwise.
    PADDING_SIDE: Optional[str] = None
    #: Extra kwargs forwarded to ``MODEL_CLS.from_pretrained()``.
    MODEL_KWARGS: Optional[dict] = None
    #: Extra kwargs forwarded to ``PROCESSOR_CLS.from_pretrained()``.
    PROCESSOR_KWARGS: Optional[dict] = None

    def __init__(self):
        super().__init__()
        cls_name = type(self).__name__
        if self.MODEL_ID is None:
            raise ValueError(
                f"{cls_name} must set the ``MODEL_ID`` class attribute "
                f"(a HuggingFace model identifier).")
        if self.MODEL_CLS is None:
            raise ValueError(
                f"{cls_name} must set the ``MODEL_CLS`` class attribute "
                f"(a ``transformers`` model class).")
        # Lazy import: avoids pulling torch/transformers into the base
        # clams-python install. Apps using this class must have the
        # ``[hf]`` extra installed.
        from clams.backends.hf import load_hf_model
        self.logger.info(f"Loading HF model from {self.MODEL_ID}")
        self.processor, self.model, self.device = load_hf_model(
            self.MODEL_ID,
            self.MODEL_CLS,
            processor_cls=self.PROCESSOR_CLS,
            dtype=self.DTYPE,
            padding_side=self.PADDING_SIDE,
            model_kwargs=self.MODEL_KWARGS,
            processor_kwargs=self.PROCESSOR_KWARGS,
        )
        self.logger.info(f"HF model loaded on {self.device}")

    def generate(
            self,
            prompt: List[str],
            system_prompt: str = '',
            images: Optional[List[List[Any]]] = None,
            audios: Optional[List[List[Any]]] = None,
            prompt_mode: str = 'turn-taking',
            **generation_params,
    ) -> List[str]:
        """
        Default implementation of the
        :py:meth:`ClamsPromptableApp.generate` contract for
        HuggingFace ``transformers`` models. Runs N prompts in one
        forward pass; returns N decoded strings.

        Each inner list of ``images`` / ``audios`` is the bundled
        content for one prompt. When both ``images`` and ``audios``
        are given they must have the same outer length (multimodal
        pairs are stitched by index). When both are ``None``, runs as
        a single text-only prompt.

        The default body is the canonical HF chat-model pipeline:
        :py:meth:`build_conversation` -> ``apply_chat_template`` ->
        ``model.generate`` -> ``batch_decode``. Subclasses can
        customize finer-grained pieces via
        :py:meth:`build_conversation` (model-specific message shape)
        and :py:meth:`build_gen_kwargs` (model-specific generation
        kwargs) without touching this method.
        """
        if images is not None and audios is not None:
            if len(images) != len(audios):
                raise ValueError(
                    f"images and audios must have the same outer length "
                    f"when both are given; got "
                    f"{len(images)} vs {len(audios)}.")
        if images is not None:
            n = len(images)
        elif audios is not None:
            n = len(audios)
        else:
            n = 1  # text-only single prompt
        if n == 0:
            return []
        gen_kwargs = self.build_gen_kwargs(**generation_params)
        try:
            conversations = [
                self.build_conversation(
                    prompt, system_prompt=system_prompt,
                    images=images[i] if images is not None else None,
                    audios=audios[i] if audios is not None else None,
                    prompt_mode=prompt_mode)
                for i in range(n)
            ]
            inputs = self.processor.apply_chat_template(
                conversations,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                padding=True,
                return_tensors="pt",
            )
            inputs = inputs.to(self.device)
            if (self.DTYPE is not None
                    and 'pixel_values' in inputs
                    and inputs['pixel_values'] is not None):
                inputs['pixel_values'] = inputs['pixel_values'].to(
                    dtype=self.DTYPE)
            generated_ids = self.model.generate(**inputs, **gen_kwargs)
            input_len = inputs.input_ids.shape[1]
            new_tokens = generated_ids[:, input_len:]
            return self.processor.batch_decode(
                new_tokens, skip_special_tokens=True)
        except Exception as e:
            self.logger.error(
                f"Error processing batch: {e}", exc_info=True)
            return [''] * n

    @staticmethod
    def build_gen_kwargs(
            max_new_tokens: int = 512,
            temperature: float = 0.0,
            top_p: float = 1.0,
            top_k: int = 50,
            **_unused,
    ) -> dict:
        """
        Translate the SDK's promptable-parameter values into
        HuggingFace ``model.generate()`` kwargs. Greedy decoding
        (``do_sample=False``) when ``temperature == 0.0``; sampled
        decoding with the given ``top_p`` / ``top_k`` otherwise.

        Subclasses MAY override to add model-specific generation
        kwargs (``num_beams``, ``repetition_penalty``, custom
        stopping criteria, ``do_sample`` overrides, etc.). The base
        implementation accepts any extra keyword args and silently
        ignores them, so subclasses can pass through the full
        ``**parameters`` dict from ``_annotate`` without filtering.
        """
        gen_kwargs = {'max_new_tokens': max_new_tokens}
        if temperature > 0:
            gen_kwargs.update({
                'do_sample': True,
                'temperature': temperature,
                'top_p': top_p,
                'top_k': top_k,
            })
        return gen_kwargs


class ParameterCaster(object):

    def __init__(self, param_spec: Dict[str, Tuple[str, bool]]):
        """
        A helper class to convert parameters passed by HTTP query strings to
        proper python data types.

        :param param_spec: A specification of a data types of parameters
        """
        self.param_spec = {pname: (python_type[ptype_str], pmultivalued) 
                           for pname, (ptype_str, pmultivalued) in param_spec.items()}

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
                valuetype, multivalued = self.param_spec[k]
                for v in vs:
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
                                # pytype will complain about the next line, but it is actually correct
                                # casted.setdefault(k, []).append(v)
                                # so doing it in a more explicit way
                                if k in casted and isinstance(casted[k], list):
                                    casted[k].append(v)
                                else:
                                    casted[k] = [v]
                        else: 
                            casted[k] = v
                # when an empty value is passed (usually as a default value)
                # just add an empty list or dict as a placeholder
                # explicit check for `len == 0` is required to prevent 
                # empty values are set for params that don't have default values
                if multivalued and len(vs) == 0:
                    if valuetype == dict:
                        casted.setdefault(k, {})
                    else:
                        casted.setdefault(k, [])
            else:
                # if the parameter is not defined in the spec, there's no easy way to figure out 
                # the user's intention whether it should be a list (multivalued) or a single value.
                if len(vs) == 1:
                    casted[k] = vs[0]
                else:
                    casted[k] = vs
        return casted  # pytype: disable=bad-return-type

    @staticmethod
    def bool_param(value) -> bool:
        """
        Helper function to convert string values to bool type.
        """
        return False if value in falsy_values else True

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
        Helper function to convert a colon-separated string into a
        single-entry dictionary. The first colon is used as the
        key-value delimiter; colons are not allowed in keys.

        :param value: a colon-separated key-value string (e.g. ``key:value``)
        :type value: str
        :returns: a single-entry dict parsed from the input
        :rtype: Dict[str, str]
        """
        k, v = value.split(map_param_kv_delimiter, 1)
        if map_param_kv_delimiter in v:
            warnings.warn(
                f"The map parameter value {value!r} contains "
                f"multiple '{map_param_kv_delimiter}' characters. "
                f"Only the first one is used as the delimiter "
                f"(key={k!r}, value={v!r}). "
                f"Colons are not allowed in map parameter keys."
            )
        return {k: v}
