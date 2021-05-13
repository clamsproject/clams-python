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
        None,
        alias="@type"
    )
    properties: Optional[Dict[str, str]]
    
    class Config:
        title = 'CLAMS Output Specification'
        extra = 'forbid'
        allow_population_by_field_name = True

                
class Input(Output):
    """
    Defines a data model that describes input specification of a CLAMS app
    """
    required: Optional[bool] = True

    class Config:
        title = 'CLAMS Input Specification'
        extra = 'forbid'
        allow_population_by_field_name = True


class RuntimeParameterValue(BaseModel):
    """ 
    Defines a data model that describes a value of a runtime parameter. 
    """
    # these names are taken from the JSON schema data types
    datatype: param_value_types
    choices: List[primitives]
    default: Optional[primitives] = None
    
    
class RuntimeParameter(BaseModel):
    """
    Defines a data model that describes a single runtime configuration of a CLAMS app. 
    Usually, an app keeps a list of these configuration specifications in the 
    ``parameters`` field. 
    """
    name: str
    value: RuntimeParameterValue
    description: str
    
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
    mmif_version: str = mmif.__version__
    wrapper_version: Optional[str]
    license: str
    wrapper_license: Optional[str]
    identifier: pydantic.AnyHttpUrl
    input: List[Input] = []
    output: List[Output] = []
    parameters: List[RuntimeParameter] = []

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
        
    def add_input(self, at_type: Union[str, vocabulary.ThingTypesBase], required: bool = False, **properties):
        if at_type not in [input.at_type for input in self.input]:
            self.input.append(Input(at_type=str(at_type), required=required, properties=dict(properties)))
            if required:
                # TODO (krim @ 5/12/21): add this *optional* input to parameter
                # see https://github.com/clamsproject/clams-python/issues/29 for discussion
                pass
        
    def add_output(self, at_type: Union[str, vocabulary.ThingTypesBase], **properties):
        if at_type not in [output.at_type for output in self.output]:
            self.output.append(Output(at_type=str(at_type), properties=dict(properties)))
    
    def add_parameter(self, name: str, description: str, value_spec: Union[dict, RuntimeParameterValue]):
        if type(value_spec) == dict:
            value_spec = RuntimeParameterValue(**value_spec)
        if name not in [param.name for param in self.parameters]:
            self.parameters.append(RuntimeParameter(name=name, description=description, value=value_spec))
        else:
            raise ValueError('name alredy exist')

if __name__ == '__main__':
    # print(AppMetadata.schema_json(indent=2))
    r_dict = {'datatype': 'string', 'choices': ['aa', 'bb'], 'default': None}
    r = RuntimeParameterValue(**r_dict)
    print(r)
    rr = RuntimeParameter(name='tmp', description='string', value=r_dict)
    print(rr)
    rr = RuntimeParameter(name='tmp', description='string', value=r)
    print(rr)
    m = AppMetadata(name='test', description='test app metadata', app_version='0.0.1', license='mit', identifier='https://google.com')
    m.add_parameter(name='tmp', description='aaa', value_spec=r_dict)
    print(m)
    m.add_parameter(name='tmp2', description='aaa', value_spec=r)
    print(m.json(indent=2))

