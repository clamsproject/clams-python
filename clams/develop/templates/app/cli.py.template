#!/usr/bin/env python3
"""
The purpose of this file is to define a thin CLI interface for your app

DO NOT CHANGE the name of the file
"""

import argparse
import sys
from contextlib import redirect_stdout

import app

import clams.app
from clams import AppMetadata


def metadata_to_argparser(app_metadata: AppMetadata) -> argparse.ArgumentParser:
    """
    Automatically generate an argparse.ArgumentParser from parameters specified in the app metadata (metadata.py).
    """

    parser = argparse.ArgumentParser(
        description=f"{app_metadata.name}: {app_metadata.description} (visit {app_metadata.url} for more info)",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # parse cli args from app parameters
    for parameter in app_metadata.parameters:
        if parameter.multivalued:
            a = parser.add_argument(
                f"--{parameter.name}",
                help=parameter.description,
                nargs='+',
                action='extend',
                type=str
            )
        else:
            a = parser.add_argument(
                f"--{parameter.name}",
                help=parameter.description,
                nargs=1,
                action="store",
                type=str)
        if parameter.choices is not None:
            a.choices = parameter.choices
        if parameter.default is not None:
            a.help += f" (default: {parameter.default}"
            if parameter.type == "boolean":
                a.help += (f", any value except for {[v for v in clams.app.falsy_values if isinstance(v, str)]} "
                           f"will be interpreted as True")
            a.help += ')'
            # then we don't have to add default values to the arg_parser
            # since that's handled by the app._refined_params() method.
    parser.add_argument('IN_MMIF_FILE', nargs='?', type=argparse.FileType('r'),
                        help='input MMIF file path, or STDIN if `-` or not provided. NOTE: When running this cli.py in '
                             'a containerized environment, make sure the container is run with `-i` flag to keep stdin '
                             'open.',
                        # will check if stdin is a keyboard, and return None if it is
                        default=None if sys.stdin.isatty() else sys.stdin)
    parser.add_argument('OUT_MMIF_FILE', nargs='?', type=argparse.FileType('w'), 
                        help='output MMIF file path, or STDOUT if `-` or not provided. NOTE: When this is set to '
                             'STDOUT, any print statements in the app code will be redirected to stderr.',
                        default=sys.stdout)
    return parser


if __name__ == "__main__":
    clamsapp = app.get_app()
    arg_parser = metadata_to_argparser(app_metadata=clamsapp.metadata)
    args = arg_parser.parse_args()
    if args.IN_MMIF_FILE:
        in_data = args.IN_MMIF_FILE.read()
        # since flask webapp interface will pass parameters as "unflattened" dict to handle multivalued parameters
        # (https://werkzeug.palletsprojects.com/en/latest/datastructures/#werkzeug.datastructures.MultiDict.to_dict)
        # we need to convert arg_parsers results into a similar structure, which is the dict values are wrapped in lists
        params = {}
        for pname, pvalue in vars(args).items():
            if pvalue is None or pname in ['IN_MMIF_FILE', 'OUT_MMIF_FILE']:
                continue
            elif isinstance(pvalue, list):
                params[pname] = pvalue
            else:
                params[pname] = [pvalue]
        if args.OUT_MMIF_FILE.name == '<stdout>':
            with redirect_stdout(sys.stderr):
                out_mmif = clamsapp.annotate(in_data, **params)
        else:
            out_mmif = clamsapp.annotate(in_data, **params)
        args.OUT_MMIF_FILE.write(out_mmif)
    else:
        arg_parser.print_help()
        sys.exit(1)
