import argparse
import pathlib
import re
import shutil
from string import Template
from typing import List

import clams

update_tmp_suffix = '.tmp'
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
        self.outdir = pathlib.Path(outdir)
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
    
    def bake(self, update_level=0):
        print(f"Baking {self.recipes}")
        for recipe in self.recipes:
            src_dir = pathlib.Path(__file__).parent / 'templates' / available_recipes[recipe]['sourcedir']
            dst_dir = self.outdir / self.rawname / available_recipes[recipe]['targetdir']
            if recipe == 'app':
                caps = [t.capitalize() for t in self.name_tokens]
                app_vars = {
                    'CLAMS_VERSION': clams.__version__,
                    'APP_CLASS_NAME': "".join(caps),
                    'APP_NAME': " ".join(caps),
                    'APP_IDENTIFIER': '-'.join(self.name_tokens)
                }
                if update_level > 0:
                    self.reheat_app(src_dir, dst_dir, app_vars, reheat_level=update_level)
                else:
                    if dst_dir.exists():
                        raise FileExistsError(f"  {dst_dir} already exists. Did you mean `--update`? ")
                    self.bake_app(src_dir, dst_dir, app_vars)
            if recipe == 'gha':
                # There's nothing for devs to tweak GHA template, so first generation and updating are the same.
                self.bake_gha(src_dir, dst_dir)
            
    def bake_app(self, src_dir, dst_dir, templating_vars):
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

    def reheat_app(self, src_dir, dst_dir, templating_vars, reheat_level=1):
        essentials = ['app.py', 'metadata.py', 'cli.py', 'Containerfile', 'requirements.txt']
        for template in src_dir.glob("**/*.template"):
            dirname = template.relative_to(src_dir).parent
            basename = template.with_suffix('').name
            if basename not in essentials:
                # if non-essential, just skip when updating
                continue
            in_f = open(template, 'r')
            tmpl_to_compile = Template(in_f.read())
            compiled = tmpl_to_compile.safe_substitute(templating_vars)
            in_f.close()
            ori_fpath = dst_dir / dirname / basename
            if not ori_fpath.exists():
                # this file is new in this version of cookiecutter 
                with open(ori_fpath, 'w') as out_f:
                    out_f.write(compiled)
            else:
                ori_f = open(ori_fpath, 'r')
                ori_content = ori_f.read()
                if ori_content != compiled:
                    # when the target file already exists, we need to do diff & patch 
                    # TODO (krim @ 5/5/24): add update level 2 and 3 code here
                    out_fpath = f'{ori_fpath}{update_tmp_suffix}'
                    print(f'    {dst_dir / dirname / basename} already exists, generating a tmp file: {out_fpath}')
                    with open(out_fpath, 'w') as out_f:
                        out_f.write(compiled)
                else:
                    print(f'    {dst_dir / dirname / basename} already exists, but the content is unchanged from the '
                          f'template, skipping re-generating')
        print(f"App skeleton code is updated in {self.rawname}")
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
    parser.add_argument(
        '-u', '--update',
        action='count',
        default=0,  #  > Note, the default will be None unless explicitly set to 0. (https://docs.python.org/3/library/argparse.html#action)
        help=f'Set update level by passing this flag multiple times. This is EXPERIMENTAL, and developers MUST NOT'
             f'rely on the update results, and should conduct manual checks afterward. LEVEL 0: does not update and '
             f'raise an error when existing directory found. LEVEL 1: generate non-existing files and generate '
             f'`{update_tmp_suffix}`-suffixed files for existing one. LEVEL 2 (WIP): generate non-existing files and '
             f'automatically generate patch files for existing files. LEVEL 3 (WIP): generate non-existing files and '
             f'apply patches to existing files. (default: 0)'
    )
    return parser


def main(args):
    cutter = CookieCutter(name=args.name, outdir=args.parent_dir, recipes=args.recipes)
    cutter.bake(args.update)

if __name__ == '__main__':
    parser = prep_argparser()
    args = parser.parse_args()
    main(args)
