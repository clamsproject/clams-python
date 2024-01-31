import argparse
import sys
import textwrap
from pathlib import Path as P

import mmif


def is_valid_choice(choice):
    try:
        ichoice = int(choice)
        if 0 <= ichoice:
            return ichoice
        else:
            raise ValueError(f"\nInvalid argument for -n. Please enter a positive integer.")
    except ValueError:
        raise argparse.ArgumentTypeError(f"\nInvalid argument for -n. Please enter a positive integer.")

def user_choice(mmif_obj:mmif.Mmif) -> int:
    """
    Function to ask user to choose the rewind range.

    :param mmif_obj: mmif object
    :return: int option number
    """

    ## Give a user options (#, "app", "timestamp") - time order
    n = len(mmif_obj.views)
    i = 0  # option number
    # header
    print("\n" + "{:<4} {:<30} {:<100}".format("num", "timestamp", "app"))
    for view in mmif_obj.views:
        option = "{:<4} {:<30} {:<100}".format(n-i, str(view.metadata.timestamp), str(view.metadata.app))
        print(option)
        i += 1

    ## User input
    while True:
        choice = int(input("\nEnter the number to delete from that point by rewinding: "))
        try:
            if 0 <= choice <= n:
                return choice
            else:
                print(f"\nInvalid choice. Please enter an integer in the range [0, {n}].")
        except ValueError:
            print("\nInvalid input. Please enter a valid number.")


def rewind_mmif(mmif_obj: mmif.Mmif, choice: int, choice_is_viewnum: bool = True) -> mmif.Mmif:
    """
    Rewind MMIF by deleting the last N views. 
    The number of views to rewind is given as a number of "views", or number of "producer apps". 
    By default, the number argument is interpreted as the number of "views". 
    Note that when the same app is repeatedly run in a CLAMS pipeline and produces multiple views in a row,
    rewinding in "app" mode will rewind all those views at once.

    :param mmif_obj: mmif object
    :param choice: number of views to rewind
    :param choice_is_viewnum: if True, choice is the number of views to rewind. If False, choice is the number of producer apps to rewind.
    :return: rewound mmif object

    """
    if choice_is_viewnum:
        for vid in list(v.id for v in mmif_obj.views)[-1:-choice-1:-1]:
            mmif_obj.views._items.pop(vid)
    else:
        app_count = 0
        cur_app = ""
        vid_to_pop = []
        for v in reversed(mmif_obj.views):
            vid_to_pop.append(v.id)
            if app_count >= choice:
                break
            if v.metadata.app != cur_app:
                app_count += 1
                cur_app = v.metadata.app
        for vid in vid_to_pop:
            mmif_obj.views._items.pop(vid)
    return mmif_obj


def describe_argparser():
    """
    returns two strings: one-line description of the argparser, and addition material, 
    which will be shown in `clams --help` and `clams <subcmd> --help`, respectively.
    """
    oneliner = 'provides CLI to rewind a MMIF from a CLAMS pipeline.'
    additional = textwrap.dedent("""
    MMIF rewinder rewinds a MMIF by deleting the last N views.
    N can be specified as a number of views, or a number of producer apps. """)
    return oneliner, oneliner + '\n\n' + additional


def prep_argparser(**kwargs):
    parser = argparse.ArgumentParser(description=describe_argparser()[1], formatter_class=argparse.RawDescriptionHelpFormatter, **kwargs)
    parser.add_argument("mmif_file", nargs=1, help="Path to the input MMIF file, or '-' to read from stdin.")
    parser.add_argument("-o", '--output', default=None, metavar="PATH", help="Path to the rewound MMIF output file. When not given, the rewound MMIF is printed to stdout.")
    parser.add_argument("-p", '--pretty', action='store_true', help="Pretty-print rewound MMIF. True by default")
    parser.add_argument("-n", '--number', default="0", type=is_valid_choice, help="Number of views to rewind (default: interactive mode)")
    parser.add_argument("-m", '--mode', choices=['app', 'view'], default='view', help="Number of views to rewind (default: interactive mode)")
    return parser


def main(args):
    mmif_obj = mmif.Mmif(sys.stdin) if args.mmif_file[0] == '-' else mmif.Mmif(open(args.mmif_file[0]).read())

    if args.number == 0: # If user doesn't know how many views to rewind, give them choices.
        choice = user_choice(mmif_obj)
    else:
        choice = args.number

    
    if args.output:
        # Check if the same file name exist in the path and avoid overwriting.
        output_fp = P(args.output)
        if output_fp.is_file():
            parent = output_fp.parent
            stem = output_fp.stem
            suffix = output_fp.suffix
            count = 1
            while (parent / f"{stem}_{count}{suffix}").is_file():
                count += 1
            output_fp = parent / f"{stem}_{count}{suffix}"
        
        out_f = open(output_fp, 'w')
    else:
        out_f = sys.stdout
    out_f.write(rewind_mmif(mmif_obj, choice, args.mode == 'view').serialize(pretty=args.pretty))


if __name__ == "__main__":
    parser = prep_argparser()
    args = parser.parse_args()
    main(args)

