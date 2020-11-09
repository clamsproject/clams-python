from typing import Dict, Type

from clams.serve import *
from clams.serve import __all__ as serve_all
from clams.restify import Restifier
from clams.source import PipelineSource, SourceCli
from clams.utils import Cli
from clams.ver import __version__


__all__ = ['Restifier', 'PipelineSource'] + serve_all

CLIS: Dict[str, Type[Cli]] = {
    'source': SourceCli,
}


def cli():
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('verb', type=str, nargs='?', choices=['source', 'version'])
    parser.add_argument(
        '-v', '--version',
        action='store_true',
        help='Print CLAMS version information'
    )
    args = parser.parse_args(sys.argv[1:2])
    if args.version:
        print(__version__)
    if args.verb:
        if args.verb == 'version':
            print(__version__)
        else:
            CLIS[args.verb]().run()
