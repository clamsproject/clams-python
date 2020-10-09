from abc import ABC, abstractmethod
import json


__all__ = ['ClamsApp']


class ClamsApp(ABC):
    def __init__(self):
        self.metadata = self.setupmetadata()
        super().__init__()

    def appmetadata(self):
        return json.dumps(self.metadata)

    @abstractmethod
    def setupmetadata(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def sniff(self, mmif) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def annotate(self, mmif) -> str:
        raise NotImplementedError()
