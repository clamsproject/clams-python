from typing import Dict, Type

from clams.serve import *
from clams.serve import __all__ as serve_all
from clams.restify import Restifier
from clams.source import PipelineSource, SourceCli
from clams.utils import Cli


__all__ = ['Restifier', 'PipelineSource'] + serve_all


CLIS: Dict[str, Type[Cli]] = {
    'source': SourceCli
}


def cli():
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('verb', type=str, choices=['source'])
    args = parser.parse_args(sys.argv[1:2])
    if args.verb:
        CLIS[args.verb]().run()
