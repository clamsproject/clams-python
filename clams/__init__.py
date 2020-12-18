from clams.app import *
from clams.app import __all__ as serve_all
from clams.restify import Restifier
from clams import source
from clams.source import PipelineSource
from clams.ver import __version__

__all__ = ['Restifier', 'PipelineSource'] + serve_all


def prep_argparser():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=__version__
    )
    subparsers = parser.add_subparsers()
    subparsers._name_parser_map['source'] = source.prep_argparser()
    return parser


def cli():
    parser = prep_argparser()
    args = parser.parse_args()

    if args.documents:
        print(source.generate_source_mmif(**vars(args)))
