import argparse
import pathlib
import re
import shutil
from string import Template

import clams


class CookieCutter(object):
    
    def __init__(self, name:str, outdir:str, ghactions:bool=True):
        self.rawname = name 
        self.name_tokens = self.tokenize_rawname()
        self.ourdir = pathlib.Path(outdir)
        self.copy_gha = ghactions
        
    def tokenize_rawname(self):
        word_pat = re.compile('[A-Z][a-z]+|[0-9A-Z]+(?=[A-Z][a-z])|[0-9A-Z]{2,}|[a-z0-9]{2,}|[a-zA-Z0-9]')
        words = [m.group(0).lower() for m in word_pat.finditer(self.rawname)]
        if words[0] == 'app':
            words.pop(0)
        if words[-1] == 'app':
            words.pop()
        return words
    
    def bake(self):
        src_dir = pathlib.Path(__file__).parent / 'templates' / 'app'
        dst_dir = self.ourdir / self.rawname
        excludes = {'__init__.py'}
        caps = [t.capitalize() for t in self.name_tokens]
        templating_vars = {
            'CLAMS_VERSION': clams.__version__,
            'APP_CLASS_NAME': "".join(caps),
            'APP_NAME': " ".join(caps),
            'APP_IDENTIFIER': '-'.join(self.name_tokens)
        }
        for g in src_dir.glob("**/*"):
            r = g.relative_to(src_dir).parent
            f = g.name
            if r in excludes or f in excludes:
                continue
            (dst_dir / r).mkdir(exist_ok=True)
            
            with open(g, 'r') as in_f, open(dst_dir/r/f, 'w') as out_f:
                tmpl_to_compile = Template(in_f.read())
                compiled = tmpl_to_compile.safe_substitute(templating_vars)
                out_f.write(compiled)
        if self.copy_gha:
            src_dir = pathlib.Path(__file__).parent / 'templates' / 'github'
            dst_dir = dst_dir / '.github'
            shutil.copytree(src_dir, dst_dir)


def prep_argparser(**kwargs):
    """
    provides CLI to create a skeleton code for app development.
    """
    parser = argparse.ArgumentParser(**kwargs)
    parser.add_argument(
        '-r', '--recipe', 
        action='store',
        default='app',
        choices=['app'],
        help="Pick a recipe to use. Currently `app` is the only option, hence there's no need to use the flag at all."
    )
    parser.add_argument(
        '--no-github-actions',
        action='store_true', 
        help='The cookiecutter by default assumes that the app codebase will be hosted on `github.com/clamsproejct`, '
             'and add pre-shipped github actions for the `clamsproject` organization setup to the skeleton codebase. '
             'Use this options to disable this behavior.'
    )
    parser.add_argument(
        '-n', '--name',
        action='store',
        required=True,
        help='The name of the directory where the baked app skeleton is placed. This name is also used to generate '
             '1) Python class name of the app, 2) values for `name` and `identifier` fields in app-metadata, '
             'based on heuristic tokenizing and casing rules. RECOMMENDATION: only use lower case alpha-numerics, '
             'do not use whitespace, use dash (`-`) character instead for word boundaries, always check for the '
             'generated names and make changes if they are incorrect. NOTE: if the name starts with `app-` or ends '
             'with `-app`, those affixes will be removed from Python class name and app identifier, but will be '
             'retained in the directory name. (e.g. `app-foo-bar-app` will be converted to `FooBar` for class name, '
             '`foo-bar-app` for app identifier, and `app-foo-bar-app` for directory name.)'
        
    )
    parser.add_argument(
        '-p', '--parent-dir',
        default='.',
        metavar='PATH',
        action='store',
        nargs='?',
        help='The name of the parent directory where the app skeleton directory is placed. (default: current directory)'
    )
    return parser


def main(args):
    cutter = CookieCutter(name=args.name, outdir=args.parent_dir, ghactions=not args.no_github_actions)
    cutter.bake()

if __name__ == '__main__':
    parser = prep_argparser()
    args = parser.parse_args()
    main(args)
