from clams.app import *
from clams.app import __all__ as app_all
from clams.appmetadata import AppMetadata
from clams.restify import Restifier
from clams import source
from clams.source import PipelineSource
from clams.ver import __version__
from mmif import __specver__

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
    subparsers = parser.add_subparsers()
    subparsers._name_parser_map['source'] = source.prep_argparser()
    return parser


def cli():
    parser = prep_argparser()
    args = parser.parse_args()

    if args.documents:
        print(source.generate_source_mmif(**vars(args)))
