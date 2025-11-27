
from clams.appmetadata import AppMetadata
from mmif.vocabulary import DocumentTypes, AnnotationTypes

def appmetadata() -> AppMetadata:
    metadata = AppMetadata(
        name="Example Clams App",
        description="An example app for testing.",
        app_license="MIT",
        identifier="example-app",
        url="http://example.com/example-app",
    )
    metadata.add_input(DocumentTypes.TextDocument)
    metadata.add_input_oneof(DocumentTypes.VideoDocument, DocumentTypes.AudioDocument)
    metadata.add_output(AnnotationTypes.TimeFrame)
    metadata.add_parameter(name='raise_error', description='a dummy parameter', type='boolean', default=False)
    return metadata
