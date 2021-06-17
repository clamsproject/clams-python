import sys

from mmif import __specver__

from clams import source
from clams.app import *
from clams.app import __all__ as app_all
from clams.appmetadata import AppMetadata
from clams.restify import Restifier
from clams.source import PipelineSource
from clams.ver import __version__

__all__ = [AppMetadata, 'Restifier', 'PipelineSource'] + app_all
version_template = "{} (based on MMIF spec: {})"


def prep_argparser():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=version_template.format(__version__, __specver__)
    )
    subparsers = parser.add_subparsers(dest='subcmd')
    subparsers.add_parser('source', parents=[source.prep_argparser()], add_help=False)
    return parser


def cli():
    parser = prep_argparser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()
    if args.subcmd == 'source':
        source.main(args)
