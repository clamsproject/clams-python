from mmif import AnnotationTypes, DocumentTypes

from clams import AppMetadata


def appmetadata() -> AppMetadata:
    metadata = AppMetadata(
        name="Example CLAMS App for testing",
        description="This app doesn't do anything",
        app_license="MIT",
        identifier=f"https://apps.clams.ai/example",
        output=[{'@type': AnnotationTypes.TimeFrame}],
        dependencies=['clams-python==develop-ver', 'mmif-pyhon==0.0.999'],
        url="https://fakegithub.com/some/repository"
    )
    metadata.add_input(DocumentTypes.AudioDocument)
    metadata.add_parameter(name='raise_error', description='force raise a ValueError',
                           type='boolean', default='false')
    return metadata
