import os
from typing import Union, Dict, List

import mmif
import pydantic
from mmif import vocabulary
from typing_extensions import Literal

primitives = Union[int, float, str, bool]
# these names are taken from the JSON schema data types
param_value_types = Literal['integer', 'number', 'string', 'boolean']


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


def get_mmif_specver():
    return mmif.__specver__


class _BaseModel(pydantic.BaseModel):
    
    class Config:
        def schema_extra(schema, model) -> None:
            for prop in schema.get('properties', {}).values():
                prop.pop('title', None)


class Output(_BaseModel):
    """
    Defines a data model that describes output specification of a CLAMS app
    """
    at_type: pydantic.AnyHttpUrl = pydantic.Field(..., alias="@type", description="The type of the object. Must be a IRI string.")
    properties: Dict[str, str] = pydantic.Field({}, description="(optional) Specification for type properties, if any.")
    
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
    required: bool = pydantic.Field(None, description="(optional) Indicating whether this input type is mandatory or optional.")

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
    Usually, an app keeps a list of these configuration specifications in the 
    ``parameters`` field. 
    """
    name: str = pydantic.Field(..., description="A short name of the parameter (works as a key).")
    description: str = pydantic.Field(..., description="A longer description of the parameter (what it does, how to use, etc.).")
    type: param_value_types = pydantic.Field(..., description=f"Type of the parameter value the app expects. Must be one of {param_value_types.__values__}.")  # pytype: disable=attribute-error
    choices: List[primitives] = pydantic.Field(None, description="(optional) List of string values that can be accepted.")
    default: primitives = pydantic.Field(None, description="(optional) Default value for the parameter. Only valid for optional parameters.")
    
    class Config:
        title = 'CLAMS App Runtime Parameter'
        extra = 'forbid'
        
        
class AppMetadata(pydantic.BaseModel):
    """
    Defines a data model that describes a CLAMS app. 
    Can be initialized by simply passing all required key-value pairs. If you 
    have a pre-generated metadata as an external file, you can read in the file 
    as a ``dict`` and use it as keyword arguments for initialization. 
    
    Please refer to <:ref:`appmetadata`> for the metadata specification. 
    """
    name: str = pydantic.Field(..., description="A short name of the app.")
    description: str = pydantic.Field(..., description="A longer description of the app (what it does, how to use, etc.).")
    app_version: str = pydantic.Field(..., description="Version of the app.")
    mmif_version: str = pydantic.Field(default_factory=get_mmif_specver, description="Version of MMIF specification the app. When the metadata is generated using clams-python SDK, this field is automatically filled in.")
    wrappee_version: str = pydantic.Field(None, description="(optional) Version of wrapped software, if the app is working as a wrapper. ")
    license: str = pydantic.Field(..., description="License information of the app.")
    wrappee_license: str = pydantic.Field(None, description="(optional) License information of wrapped software, if the app is working as a wrapper. ")
    identifier: pydantic.AnyHttpUrl = pydantic.Field(..., description="IRI-formatted unique identifier for the app.")
    input: List[Input] = pydantic.Field([], description="List of input types. Must have at least one.")
    output: List[Output] = pydantic.Field([], description="List of output types. Must have at least one.")
    parameters: List[RuntimeParameter] = pydantic.Field([], description="List of runtime parameters. Can be empty.")

    class Config:
        title = "CLAMS AppMetadata"
        extra = 'forbid'
        allow_population_by_field_name = True

        @staticmethod
        def schema_extra(schema, model) -> None:
            for prop in schema.get('properties', {}).values():
                prop.pop('title', None)
            schema['$schema'] = "http://json-schema.org/draft-07/schema#"  # currently pydantic doesn't natively support the $schema field. See https://github.com/samuelcolvin/pydantic/issues/1478
            schema['$comment'] = f"clams-python SDK {get_clams_pyver()} was used to generate this schema"  # this is only to hold version information
        
    def add_input(self, at_type: Union[str, vocabulary.ThingTypesBase], required: bool = True, **properties):
        """
        Helper method to add an element to the ``input`` list. 
        
        :param at_type: ``@type`` of the input object
        :param required: whether this type is mandatory or optional 
        :param properties: additional property specifications
        """
        new_inp = Input(at_type=at_type, required=required)
        if len(properties) > 0:
            new_inp.properties = properties
        if new_inp not in self.input:
            self.input.append(new_inp)
            if not required:
                # TODO (krim @ 5/12/21): automatically add *optional* input types to parameter
                # see https://github.com/clamsproject/clams-python/issues/29 for discussion
                pass
        
    def add_output(self, at_type: Union[str, vocabulary.ThingTypesBase], **properties):
        """
        Helper method to add an element to the ``output`` list. 
        
        :param at_type: ``@type`` of the input object
        :param properties: additional property specifications
        """
        if at_type not in [output.at_type for output in self.output]:
            if len(properties) > 0:
                self.output.append(Output(at_type=str(at_type), properties=dict(properties)))
            else:
                self.output.append(Output(at_type=str(at_type)))
        else:
            raise ValueError(f"output '{at_type}' already exist.")
    
    def add_parameter(self, **parameter_spec):
        """
        Helper method to add an element to the ``parameters`` list. 
        
        :param parameter_spec: key-value pairs that specify a RuntimeParameter. See ``RuntimeParameter`` section of <:ref:`appmetadata`> for keys and values that are accepted.
        """
        new_param = RuntimeParameter(**parameter_spec)
        if new_param.name not in [param.name for param in self.parameters]:
            self.parameters.append(new_param)
        else:
            raise ValueError(f"parameter '{new_param.name}' already exist.")

if __name__ == '__main__':
    print(AppMetadata.schema_json(indent=2))
