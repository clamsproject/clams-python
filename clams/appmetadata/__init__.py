from typing import Optional, Union, Dict, List

import mmif
import pydantic
from mmif import vocabulary
from typing_extensions import Literal

import clams

primitives = Union[int, float, str, bool]
param_value_types = Literal['integer', 'number', 'string', 'boolean']


class BaseModel(pydantic.BaseModel):
    
    class Config:
        def schema_extra(schema, model) -> None:
            for prop in schema.get('properties', {}).values():
                prop.pop('title', None)


class Output(BaseModel):
    """
    Defines a data model that describes output specification of a CLAMS app
    """
    at_type: pydantic.AnyHttpUrl = pydantic.Field(
        ...,
        alias="@type"
    )
    properties: Dict[str, str] = {}
    
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
    required: bool = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.required is None:
            self.required = True

    class Config:
        title = 'CLAMS Input Specification'
        extra = 'forbid'
        allow_population_by_field_name = True


class RuntimeParameter(BaseModel):
    """
    Defines a data model that describes a single runtime configuration of a CLAMS app. 
    Usually, an app keeps a list of these configuration specifications in the 
    ``parameters`` field. 
    """
    name: str
    description: str
    type: param_value_types  # these names are taken from the JSON schema data types
    choices: Optional[List[primitives]]
    default: Optional[primitives]
    
    class Config:
        title = 'CLAMS App Runtime Parameter'
        extra = 'forbid'
        

class AppMetadata(pydantic.BaseModel):
    """
    Defines a data model that describes a CLAMS app
    """
    name: str
    description: str
    app_version: str
    mmif_version: str = None
    wrapper_version: Optional[str]
    license: str
    wrapper_license: Optional[str]
    identifier: pydantic.AnyHttpUrl
    input: List[Input] = None
    output: List[Output] = None
    parameters: List[RuntimeParameter] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mmif_version = mmif.__version__
        if self.input is None:
            self.input = []
        if self.output is None:
            self.output = []
        if self.parameters is None:
            self.parameters = []

    class Config:
        title = "CLAMS AppMetadata"
        extra = 'forbid'
        allow_population_by_field_name = True

        @staticmethod
        def schema_extra(schema, model) -> None:
            for prop in schema.get('properties', {}).values():
                prop.pop('title', None)
            schema['$schema'] = "http://json-schema.org/draft-07/schema#"  # currently pydantic doesn't natively support the $schema field. See https://github.com/samuelcolvin/pydantic/issues/1478
            schema['$comment'] = f"clams-python SDK {clams.__version__} was used to generate this schema"  # this is only to hold version information
        
    def add_input(self, at_type: Union[str, vocabulary.ThingTypesBase], required: bool = True, **properties):
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
        if at_type not in [output.at_type for output in self.output]:
            if len(properties) > 0:
                self.output.append(Output(at_type=str(at_type), properties=dict(properties)))
            else:
                self.output.append(Output(at_type=str(at_type)))
        else:
            raise ValueError(f"output '{at_type}' already exist.")
    
    def add_parameter(self, **parameter_spec):
        new_param = RuntimeParameter(**parameter_spec)
        if new_param.name not in [param.name for param in self.parameters]:
            self.parameters.append(new_param)
        else:
            raise ValueError(f"parameter '{new_param.name}' already exist.")

if __name__ == '__main__':
    print(AppMetadata.schema_json(indent=2))
