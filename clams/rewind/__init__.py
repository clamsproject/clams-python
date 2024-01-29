import argparse
import mmif
import json
import os

def read_mmif(mmif_file)->mmif.Mmif:
    """
    Function to read mmif file and return the mmif object.
    (Would it be better to be a mmif object?)

    :param mmif_file: file path to the mmif.
    :return: mmif object
    """
    try:
        with open(mmif_file, 'r') as file:
            mmif_data = json.load(file)

        print(f"\nSuccessfully loaded MMIF file: {mmif_file}")

        mmif_obj = mmif.Mmif(mmif_data)


    except FileNotFoundError:
        print(f"Error: MMIF file '{mmif_file}' not found.")


    except Exception as e:
        print(f"Error: An unexpected error occurred - {e}")

    return mmif_obj


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
        option = "{:<4} {:<30} {:<100}".format(i, str(view.metadata.timestamp), str(view.metadata.app))



        print(option)
        i += 1

    ## User input
    while True:
        try:
            choice = int(input("\nEnter the number to delete from that point by rewinding: "))
            if 0 <= choice <= n - 1:
                return choice
            else:
                print(f"\nInvalid choice. Please enter a number between 0 and {n - 1}")
        except ValueError:
            print("\nInvalid input. Please enter a valid number.")


def process_mmif_from_user_choice(mmif_obj, choice: int, output_fp = "rewound.mmif", p=True) -> None:
    """
    Process rewinding of mmif data from user choice and save it in as a json file.

    :param mmif_obj: mmif object
    :param choice: integer to rewind from
    :param output_fp: path to save the rewound output file
    :return: rewound.mmif saved
    """
    n = len(mmif_obj.views) - choice
    mmif_obj.views.__delete_last(n)
    mmif_serialized = mmif_obj.serialize(pretty=p)

    # Check if the same file name exist in the path and avoid overwriting.
    if os.path.exists(output_fp):
        file_name, file_extension = os.path.splitext(output_fp)
        count = 1
        while os.path.exists(f"{file_name}_{count}.mmif"):
            count += 1
        output_fp = f"{file_name}_{count}.mmif"

    with open(output_fp, 'w') as mmif_file:
        mmif_file.write(mmif_serialized)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process MMIF file.")
    parser.add_argument("mmif_file", help="Path to the MMIF file")
    parser.add_argument("-o", '--output', type=str, help="Path to the rewound MMIF output file (default: rewound.mmif)")
    parser.add_argument("-p", '--pretty', help="Pretty print (default: pretty=True)")
    args = parser.parse_args()

    mmif_obj = read_mmif(args.mmif_file)
    choice = user_choice(mmif_obj)
    process_mmif_from_user_choice(mmif_obj, choice, args.output, args.pretty)
