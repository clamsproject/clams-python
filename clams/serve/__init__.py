from abc import ABC, abstractmethod


__all__ = ['ClamsApp', 'ClamApp']


class ClamsApp(ABC):
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


class ClamApp(ClamsApp, ABC):
    """ Equivalent to `ClamsApp`. This class is only for backward compatibility. Use `ClamsApp` instead. """
    pass


