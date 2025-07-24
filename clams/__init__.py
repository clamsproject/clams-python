import argparse
import sys

import mmif
from clams import develop
from clams.app import *
from clams.app import __all__ as app_all
from clams.appmetadata import AppMetadata
from clams.restify import Restifier
from clams.ver import __version__

__all__ = [AppMetadata, Restifier] + app_all
version_template = "{} (based on MMIF spec: {})"


def prep_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=version_template.format(__version__, mmif.__specver__)
    )
    subparsers = parser.add_subparsers(title='sub-command', dest='subcmd')
    return parser, subparsers


def cli():
    parser, subparsers = prep_argparser()
    cli_modules = {}
    # thinly wrap all `mmif` subcommands
    # this is primarily for backward compatibility for `souce` and `rewind` subcmds
    to_register = list(mmif.find_all_modules('mmif.utils.cli'))
    # then add my own subcommands
    to_register.append(develop)
    for cli_module in to_register:
        cli_module_name = cli_module.__name__.rsplit('.')[-1]
        cli_modules[cli_module_name] = cli_module
        subcmd_parser = cli_module.prep_argparser(add_help=False)
        subparsers.add_parser(cli_module_name, parents=[subcmd_parser],
                              help=cli_module.describe_argparser()[0],
                              description=cli_module.describe_argparser()[1],
                              formatter_class=argparse.RawDescriptionHelpFormatter,
                              )
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()
    if args.subcmd not in cli_modules:
        parser.print_help(sys.stderr)
    else:
        cli_modules[args.subcmd].main(args)

if __name__ == '__main__':
    cli()