from abc import ABC, abstractmethod


class ClamApp(ABC):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def appmetadata(self):
        raise NotImplementedError()

    @abstractmethod
    def sniff(self, mmif):
        raise NotImplementedError()

    @abstractmethod
    def annotate(self, mmif):
        raise NotImplementedError()

