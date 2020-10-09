from abc import ABC, abstractmethod
import json


__all__ = ['ClamsApp']


class ClamsApp(ABC):
    def __init__(self):
        # TODO (krim @ 10/9/20): eventually we might end up with a python class
        # for this metadata (with a JSON schema)
        self.metadata: dict = self.setupmetadata()
        super().__init__()

    def appmetadata(self):
        # TODO (krim @ 10/9/20): when self.metadata is no longer a `dict`
        # this method might needs to be changed to properly serialize input
        return json.dumps(self.metadata)

    @abstractmethod
    def setupmetadata(self) -> dict:
        raise NotImplementedError()

    @abstractmethod
    def sniff(self, mmif) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def annotate(self, mmif) -> str:
        raise NotImplementedError()
