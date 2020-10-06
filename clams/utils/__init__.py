import sys
import abc


class Cli(abc.ABC):
    def __init__(self):
        self.args = sys.argv[2:]

    def run(self):
        raise NotImplementedError()
