import os
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Union, Dict, List, Optional, Literal

import mmif
import pydantic
from mmif import vocabulary

unresolved_app_version_num = 'unresolvable'
app_version_envvar_key = 'CLAMS_APP_VERSION'
# type aliases to use in app metadata and runtime parameter processing 
primitives = Union[int, float, bool, str]
# these names are taken from the JSON schema data types
param_value_types = Literal['integer', 'number', 'string', 'boolean']

param_value_types_values = param_value_types.__args__  # pytype: disable=attribute-error
app_directory_baseurl = "http://apps.clams.ai"


def get_clams_pyver():
    # real hack to avoid import clams as a package in gh-action workflow
    try:
        import clams
        return clams.__version__
    except ImportError:
        version_fname = os.path.join(os.path.dirname(__file__), '..', '..', 'VERSION')
        if os.path.exists(version_fname):
            with open(version_fname) as version_f:
                return version_f.read().strip()
        else:
            raise Exception('cannot find clams-python version')


def generate_app_version(cwd=None):
    gitcmd = shutil.which('git') 
    gitdir = (Path(sys.modules["__main__"].__file__).parent.resolve() if cwd is None else Path(cwd)) / '.git'
    if gitcmd is not None and gitdir.exists():
        proc = subprocess.run([gitcmd, '--git-dir', str(gitdir), 'describe', '--tags', '--always'], 
                              capture_output=True, check=True)
        return proc.stdout.decode('utf8').strip()
    elif app_version_envvar_key in os.environ:
        return os.environ[app_version_envvar_key]
    else:
        return unresolved_app_version_num


def get_mmif_specver():
    return mmif.__specver__


class _BaseModel(pydantic.BaseModel):
    
    class Config:
        @staticmethod
        def json_schema_extra(schema, model) -> None:
            for prop in schema.get('properties', {}).values():
                prop.pop('title', None)


class Output(_BaseModel):
    """
    Defines a data model that describes output specification of a CLAMS app
    """
    at_type: pydantic.AnyHttpUrl = pydantic.Field(
        ..., 
        alias="@type", 
        description="The type of the object. Must be a IRI string."
    )
    properties: Dict[str, str] = pydantic.Field(
        {}, 
        description="(optional) Specification for type properties, if any."
    )
    
    @pydantic.validator('at_type', pre=True)
    def at_type_must_be_str(cls, v):
        if not isinstance(v, str):
            return str(v)
        return v

    class Config:
        title = 'CLAMS Output Specification'
        extra = 'forbid'
        allow_population_by_field_name = True

                
class Input(Output):
    """
    Defines a data model that describes input specification of a CLAMS app
    """
    required: bool = pydantic.Field(
        None, 
        description="(optional, True by default) Indicating whether this input type is mandatory or optional."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.required is None:
            self.required = True

    class Config:
        title = 'CLAMS Input Specification'
        extra = 'forbid'
        allow_population_by_field_name = True


class RuntimeParameter(_BaseModel):
    """
    Defines a data model that describes a single runtime configuration of a CLAMS app. 
    Usually, an app keeps a list of these configuration specifications in the ``parameters`` field. 
    When initializing a RuntimeParameter object in python the value for the default field must be a string. 
    For example, if you want to set a default value for a boolean parameter, use any of ``'True'``, ``'true'``, ``'t'``,
    or their falsy counterpart, instead of ``True`` or ``False``
    """
    name: str = pydantic.Field(
        ..., 
        description="A short name of the parameter (works as a key)."
    )
    description: str = pydantic.Field(
        ...,
        description="A longer description of the parameter (what it does, how to use, etc.)."
    )
    type: param_value_types = pydantic.Field(
        ...,
        description=f"Type of the parameter value the app expects. Must be one of {param_value_types_values}."
    ) 
    choices: List[primitives] = pydantic.Field(
        None, 
        description="(optional) List of string values that can be accepted."
    )
    default: primitives = pydantic.Field(
        None, 
        description="(optional) Default value for the parameter. Only valid for optional parameters. Namely, setting "
                    "a default value makes a parameter 'optional'."
    )
    multivalued: bool = pydantic.Field(
        ..., 
        description="(optional, False by default) Set True if the parameter can have multiple values.\n\n"
                    "Note that, for parameters that allow multiple values, the SDK will pass a singleton list to "
                    "``_annotate()`` even when one value is passed via HTTP.")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.multivalued is None:
            self.multivalued = False
            
    class Config:
        title = 'CLAMS App Runtime Parameter'
        extra = 'forbid'
        
        
class AppMetadata(pydantic.BaseModel):
    """
    Defines a data model that describes a CLAMS app. 
    
    Can be initialized by simply passing all required key-value pairs. 
    
    If you have a pre-generated metadata as an external file, you can read in the file as a ``dict`` and use it as 
    keyword arguments for initialization. But be careful with keys of which values are automatically generated by the 
    SDK. 
    
    
    Please refer to <:ref:`appmetadata`> for the metadata specification. 
    """
    # make sure to use two line feeds in description field when needed, that will make newline in compiled html page
    name: str = pydantic.Field(
        ...,
        description="A short name of the app."
    )
    description: str = pydantic.Field(
        ...,
        description="A longer description of the app (what it does, how to use, etc.)."
    )
    app_version: str = pydantic.Field(
        default_factory=generate_app_version,
        description="(AUTO-GENERATED, DO NOT SET MANUALLY)\n\n"
                    "Version of the app.\n\n"
                    "When the metadata is generated using clams-python SDK, this field is automatically filled in"
    )
    mmif_version: str = pydantic.Field(
        default_factory=get_mmif_specver, 
        description="(AUTO-GENERATED, DO NOT SET MANUALLY)\n\n"
                    "Version of MMIF specification the app.\n\n"
                    "When the metadata is generated using clams-python SDK, this field is automatically filled in."
    )
    analyzer_version: str = pydantic.Field(
        None, 
        description="(optional) Version of an analyzer software, if the app is working as a wrapper for one. "
    )
    app_license: str = pydantic.Field(
        ..., 
        description="License information of the app."
    )
    analyzer_license: str = pydantic.Field(
        None,
        description="(optional) License information of an analyzer software, if the app works as a wrapper for one. "
    )
    identifier: pydantic.AnyHttpUrl = pydantic.Field(
        ..., 
        description="(partly AUTO-GENERATED)\n\n"
                    "IRI-formatted unique identifier for the app.\n\n"
                    "If the app is to be published to the CLAMS app-directory, the developer should give a single "
                    "string value composed with valid URL characters (no ``/``, no whitespace),\n\n"
                    "then when the metadata is generated using clams-python SDK, the app-directory URL is prepended "
                    "and ``app_version`` value will be appended automatically.\n\n"
                    "For example, ``example-app`` -> ``http://apps.clams.ai/example-app/1.0.0``\n\n"
                    "Otherwise, only the ``app_version`` value is used as suffix, so use an IRI form, but leave the "
                    "version number out."
    )
    url: pydantic.AnyHttpUrl = pydantic.Field(
        ..., 
        description="A public repository where the app's source code (git-based) and/or documentation is available. "
    )
    input: List[Union[Input, List[Input]]] = pydantic.Field(
        [],
        description="List of input types. Must have at least one element.\n\n"
                    "This list should iterate all input types in an exhaustive and meticulous manner, meaning it is "
                    "recommended for developers to pay extra attention to ``input`` and ``output`` fields to include "
                    "1) all types are listed, 2) if types to have specific properties, include the properties.\n\n"
                    "This list should interpreted conjunctive (``AND``).\n\n"
                    "However, a nested list in this list means ``oneOf`` disjunctive (``OR``) specification.\n\n"
                    "For example, ``input = [TypeA (req=True), [TypeB, TypeC]]`` means``TypeA`` is required and either "
                    "``TypeB`` or ``TypeC`` is additionally required.\n\n"
                    "All input elements in the nested list must not be ``required=False``, and only a single nesting "
                    "level is allowed (e.g. ``input = [TypeA, [ [TypeB, TypeC], [TypeD, TypeE] ] ]`` is not allowed)."
    )
    output: List[Output] = pydantic.Field(
        [], 
        description="List of output types. Must have at least one element."
                    "This list should iterate all output types in an exhaustive and meticulous manner, meaning it is "
                    "recommended for developers to pay extra attention to ``input`` and ``output`` fields to include "
    )
    parameters: List[RuntimeParameter] = pydantic.Field(
        [],
        description="List of runtime parameters. Can be empty."
    )
    dependencies: List[str] = pydantic.Field(
        None,
        description="(optional) List of software dependencies of the app. \n\n"
                    "This list is completely optional, as in most cases such dependencies are specified in a separate "
                    "file in the codebase of the app (for example, ``requirements.txt`` file for a Python app, or "
                    "``pom.xml`` file for a maven-based Java app).\n\n"
                    "List items must be strings, not any kind of structured data. Thus, it is recommended to include "
                    "a package name and its version in the string value at the minimum (e.g., ``clams-python==1.2.3``)."
    )
    more: Dict[str, str] = pydantic.Field(
        None, 
        description="(optional) A string-to-string map that can be used to store any additional metadata of the app."
    )

    class Config:
        title = "CLAMS AppMetadata"
        extra = 'forbid'
        allow_population_by_field_name = True

        @staticmethod
        def json_schema_extra(schema, model) -> None:
            for prop in schema.get('properties', {}).values():
                prop.pop('title', None)
            schema['$schema'] = "http://json-schema.org/draft-07/schema#"  # currently pydantic doesn't natively support the $schema field. See https://github.com/samuelcolvin/pydantic/issues/1478
            schema['$comment'] = f"clams-python SDK {get_clams_pyver()} was used to generate this schema"  # this is only to hold version information

    @pydantic.validator('identifier', pre=True)
    def append_version(cls, val):
        prefix = f'{app_directory_baseurl if "/" not in val else""}'
        suffix = generate_app_version()
        return '/'.join(map(lambda x: x.strip('/'), filter(None, (prefix, val, suffix))))

    @pydantic.validator('mmif_version', pre=True)
    def auto_mmif_version(cls, val):
        return get_mmif_specver()
    
    @pydantic.validator('app_version', pre=True)
    def auto_app_version(cls, val):
        return generate_app_version()
    
    def _check_input_duplicate(self, a_input):
        for elem in self.input:
            if isinstance(elem, list):
                for nested_elem in elem:
                    if nested_elem == a_input:
                        return True
            else:
                if elem == a_input:
                    return True
        return False

    def add_input(self, at_type: Union[str, vocabulary.ThingTypesBase], required: bool = True, **properties):
        """
        Helper method to add an element to the ``input`` list. 
        
        :param at_type: ``@type`` of the input object
        :param required: whether this type is mandatory or optional 
        :param properties: additional property specifications
        """
        new = Input(at_type=at_type, required=required)
        if len(properties) > 0:
            new.properties = properties
        if self._check_input_duplicate(new):
            raise ValueError(f"Cannot add a duplicate input '{new}'.")
        else:
            self.input.append(new)
            if not required:
                # TODO (krim @ 5/12/21): automatically add *optional* input types to parameter
                # see https://github.com/clamsproject/clams-python/issues/29 for discussion
                pass

    def add_input_oneof(self, *inputs: Union[str, Input, vocabulary.ThingTypesBase] ):
        newinputs = []
        if len(inputs) == 1:
            if isinstance(inputs[0], Input):
                if not self._check_input_duplicate(inputs[0]):
                    self.input.append(inputs[0])
            else:
                self.add_input(at_type=inputs[0])

        else:
            for i in inputs:
                if not isinstance(i, Input):
                    i = Input(at_type=i)
                if not i.required:
                    raise ValueError(f"Input type in `oneOf` specification cannot be optional: {i}")
                if self._check_input_duplicate(i) or i in newinputs:
                    raise ValueError(f"Cannot add a duplicate input '{i}'.")
                else:
                    newinputs.append(i)
            self.input.append(newinputs)

    def add_output(self, at_type: Union[str, vocabulary.ThingTypesBase], **properties):
        """
        Helper method to add an element to the ``output`` list. 
        
        :param at_type: ``@type`` of the input object
        :param properties: additional property specifications
        """
        new = Output(at_type=at_type)
        if len(properties) > 0:
            new.properties = properties
        if new not in self.output:
            self.output.append(new)
        else:
            raise ValueError(f"Cannot add a duplicate output '{new}'.")

    def add_parameter(self, name: str, description: str, type: param_value_types,
                      choices: Optional[List[primitives]] = None,
                      multivalued: bool = False,
                      default: primitives = None):
        """
        Helper method to add an element to the ``parameters`` list. 
        """
        # casting default values (when the value is not nothing) makes sure 
        # the values are correctly casted by the pydantic
        # see https://docs.pydantic.dev/1.10/usage/types/#unions
        # e.g. casting 0.1 using the `primitives` dict will result in  0 (int)
        # while casting "0.1" using the `primitives` dict will result in  0.1 (float)
        new_param = RuntimeParameter(name=name, description=description, type=type,
                                     choices=choices, default=str(default) if default else default, multivalued=multivalued)
        if new_param.name not in [param.name for param in self.parameters]:
            self.parameters.append(new_param)
        else:
            raise ValueError(f"parameter '{new_param.name}' already exist.")
        
    def add_more(self, key: str, value: str):
        """
        Helper method to add a k-v pair to the ``more`` map. 
        :param key: key of an additional metadata
        :param value: value of the additional metadata
        """
        if len(key) > 0 and len(value) > 0: 
            if self.more is None:
                self.more = {}
            if key not in self.more:
                self.more[key] = value
            else:
                raise ValueError(f"'{key}' is already being used in the appmetadata!")
        else:
            raise ValueError("Key and value should not be empty!")
        
    def jsonify(self, pretty=False):
        if pretty:
            return self.json(exclude_defaults=True, by_alias=True, indent=2)
        else:
            return self.json(exclude_defaults=True, by_alias=True)


if __name__ == '__main__':
    print(AppMetadata.schema_json(indent=2))
