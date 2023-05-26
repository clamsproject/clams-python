import argparse
import pathlib
import re
import shutil
from string import Template
from typing import List

import clams

available_recipes = {
    'app': {
        'description': 'Skeleton code for a CLAMS app',
        'sourcedir': 'app',
        'targetdir': '.',
    },
    'gha': {
        'description': 'GtiHub Actions workflow files specific to `clamsproject` GitHub organization',
        'sourcedir': 'gha',
        'targetdir': '.github',
    }
}


class CookieCutter(object):
    
    def __init__(self, name: str, outdir: str, recipes: List[str]):
        self.rawname = name 
        self.name_tokens = self.tokenize_rawname()
        self.ourdir = pathlib.Path(outdir)
        if recipes:
            self.recipes = recipes
        else:
            self.recipes = available_recipes.keys()
        
    def tokenize_rawname(self):
        word_pat = re.compile('[A-Z][a-z]+|[0-9A-Z]+(?=[A-Z][a-z])|[0-9A-Z]{2,}|[a-z0-9]{2,}|[a-zA-Z0-9]')
        words = [m.group(0).lower() for m in word_pat.finditer(self.rawname)]
        if len(words) > 1:
            if words[0] == 'app':
                words.pop(0)
            if words[-1] == 'app':
                words.pop()
        return words
    
    def bake(self):
        print(f"Baking {self.recipes}")
        for recipe in self.recipes:
            src_dir = pathlib.Path(__file__).parent / 'templates' / available_recipes[recipe]['sourcedir']
            dst_dir = self.ourdir / self.rawname / available_recipes[recipe]['targetdir']
            if recipe == 'app':
                self.bake_app(src_dir, dst_dir)
            if recipe == 'gha':
                self.bake_gha(src_dir, dst_dir)
            
    def bake_app(self, src_dir, dst_dir):
        caps = [t.capitalize() for t in self.name_tokens]
        templating_vars = {
            'CLAMS_VERSION': clams.__version__,
            'APP_CLASS_NAME': "".join(caps),
            'APP_NAME': " ".join(caps),
            'APP_IDENTIFIER': '-'.join(self.name_tokens)
        }
        for g in src_dir.glob("**/*.template"):
            r = g.relative_to(src_dir).parent
            f = g.with_suffix('').name
            (dst_dir / r).mkdir(exist_ok=True)
            
            with open(g, 'r') as in_f, open(dst_dir/r/f, 'w') as out_f:
                tmpl_to_compile = Template(in_f.read())
                compiled = tmpl_to_compile.safe_substitute(templating_vars)
                out_f.write(compiled)
        print(f"App skeleton code is copied to {self.rawname}")
        print(f"  Checkout {self.rawname}/README.md for the next steps!")
                
    def bake_gha(self, src_dir, dst_dir):
        self.simple_recursive_copy_minus_template_suffix(src_dir, dst_dir)
        print(f"GitHub Actions workflow files are copied to {self.rawname}/.github")
        print(f"  Checkout {self.rawname}/.github/README.md for how they work!")
    
    @staticmethod
    def simple_recursive_copy_minus_template_suffix(src_dir, dst_dir):
        for g in src_dir.glob("**/*.template"):
            dst_pname = dst_dir/g.relative_to(src_dir)
            dst_pname.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(g, dst_pname.with_suffix(''))


def describe_argparser():
    """
    returns two strings: one-line description of the argparser, and addition material, 
    which will be shown in `clams --help` and `clams <subcmd> --help`, respectively.
    """
    oneliner = 'provides CLI to create a skeleton code for app development'
    additional = "Available recipes:\n"
    for k, v in available_recipes.items():
        additional += f"  - {k}: {v['description']}\n" 
    return oneliner, oneliner + '\n\n' + additional
    

def prep_argparser(**kwargs):
    parser = argparse.ArgumentParser(description=describe_argparser()[1], formatter_class=argparse.RawDescriptionHelpFormatter, **kwargs)
    parser.add_argument(
        '-r', '--recipes', 
        action='store',
        nargs='+',
        default=[],
        help=f"Pick recipes to bake. DEFAULT: {list(available_recipes.keys())}"
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
    cutter = CookieCutter(name=args.name, outdir=args.parent_dir, recipes=args.recipes)
    cutter.bake()

if __name__ == '__main__':
    parser = prep_argparser()
    args = parser.parse_args()
    main(args)
