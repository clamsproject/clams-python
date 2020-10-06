from abc import ABC, abstractmethod


__all__ = ['ClamsApp']


class ClamsApp(ABC):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def appmetadata(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def sniff(self, mmif) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def annotate(self, mmif) -> str:
        raise NotImplementedError()
