from typing import Union

from mmif import Mmif, Medium


class PipelineSource:
    """
    The PipelineSource class.

    A PipelineSource object is used at the beginning of a
    CLAMS pipeline to populate a new MMIF file with media.
    It is instantiated with a mmif_context parameter that
    populates the top-level @context property of the MMIF
    files produced.

    The same PipelineSource object can be used repeatedly
    to generate multiple MMIF objects with the same @context
    but with different constituent media. We recommend
    creating a new PipelineSource object if you want to
    use a different @context.
    """
    mmif: Mmif

    def __init__(self, mmif_context: str) -> None:
        """
        Initializes a new PipelineSource with the provided context IRI.
        :param mmif_context: the desired context IRI
        """
        self.mmif_start: dict = {"@context": mmif_context, "media": [], "views": []}
        self.prime()

    def add_medium(self, medium: Union[str, dict, Medium]) -> None:
        """
        Adds a medium to the working source MMIF.

        When you're done, fetch the source MMIF with produce().

        :param medium: the medium to add, as a JSON dict
                       or string or as a MMIF Medium object
        """
        if isinstance(medium, (str, dict)):
            medium = Medium(medium)
        self.mmif.add_medium(medium)

    def prime(self) -> None:
        """
        Primes the PipelineSource with a fresh MMIF object.

        Call this method if you want to reset the PipelineSource
        without producing a MMIF object with produce().
        """
        self.mmif = Mmif(self.mmif_start)  # , frozen=False)

    def produce(self) -> Mmif:
        """
        Returns the source MMIF and resets the PipelineSource.

        Call this method once you have added all the media for
        your pipeline.
        """
        source = self.mmif
        # source.freeze_media()
        self.prime()
        return source
