from typing import Optional, Union, Dict, List

import mmif
import pydantic

import clams

primitives = Union[int, str, bool]


class Output(pydantic.BaseModel):
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

        def schema_extra(schema, model) -> None:
            for prop in schema.get('properties', {}).values():
                prop.pop('title', None)
                
                
class Input(Output):
    """
    Defines a data model that describes input specification of a CLAMS app
    """
    required: Optional[bool] = True

    class Config:
        title = 'CLAMS Input Specification'
        extra = 'forbid'
        allow_population_by_field_name = True


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
    input: List[Input]
    output: List[Output]

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


if __name__ == '__main__':
    print(AppMetadata.schema_json(indent=2))
