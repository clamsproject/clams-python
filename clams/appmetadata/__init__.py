from typing import Optional, Union

import mmif
import pydantic

import clams

primitives = Union[int, str, bool]


class AppMetadata(pydantic.BaseModel):
    name: str
    description: str
    app_version: str
    mmif_version: str = mmif.__version__
    wrapper_version: Optional[str]
    license: str
    wrapper_license: Optional[str]
    url: pydantic.AnyHttpUrl
    input: list
    output: list

    class Config:
        title = "CLAMS AppMetadata"
        description = "CLAMS AppMetadata defines metadata model that describes a CLAMS app"
        extra = 'forbid'
        allow_population_by_field_name = True
        schema_extra = {
            '$schema': "http://json-schema.org/draft-07/schema#", # currently pydantic doesn't natively support the $schema field. See https://github.com/samuelcolvin/pydantic/issues/1478
            '$comment': f"clams-python SDK {clams.__version__} was used to generate this schema" # this is only to hold version information
        }

if __name__ == '__main__':
    print(AppMetadata.schema_json(indent=2))