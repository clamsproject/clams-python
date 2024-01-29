import argparse
import mmif
import json

def read_mmif(mmif_file):
    """
    Function to read mmif file as a json file and return it as a dictionary.
    (Would it be better to be a mmif object?)

    :param mmif_file: file path to the mmif.
    :return: dictionary with mmif data
    """
    try:
        with open(mmif_file, 'r') as file:
            mmif_data = json.load(file)

        print(f"\nSuccessfully loaded MMIF file: {mmif_file}")

    except FileNotFoundError:
        print(f"Error: MMIF file '{mmif_file}' not found.")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in MMIF file '{mmif_file}'.")
    except Exception as e:
        print(f"Error: An unexpected error occurred - {e}")

    return mmif_data


def user_choice(mmif_data):
    """
    Function to ask user to choose the rewind range.

    :param mmif_data: dictionary
    :return: int option number
    """

    ## Give a user options (#, "app", "timestamp") - time order
    n = len(mmif_data["views"])
    i = 0 # option number
    # header
    print("\n"+"{:<4} {:<30} {:<100}".format("num", "timestamp", "app"))
    for view in mmif_data["views"]:
        if "timestamp" in view["metadata"]:
            option = "{:<4} {:<30} {:<100}".format(i, view["metadata"]["timestamp"], view["metadata"]["app"])
        else:
            option = "{:<4} {:<30} {:<100}".format(i, "-", view["metadata"]["app"])
        print(option)
        i += 1

    ## User input
    while True:
        try:
            choice = int(input("\nEnter the number to delete from that point by rewinding: "))
            if 0 <= choice <= n-1:
                return choice
            else:
                print(f"\nInvalid choice. Please enter a number between 0 and {n-1}")
        except ValueError:
            print("\nInvalid input. Please enter a valid number.")


def process_mmif_from_user_choice(mmif_data, choice):
    """
    Process rewinding of mmif data from user choice and save it in as a json file.

    :param mmif_data:
    :param choice:
    :return: Output.mmif
    """
    mmif_data["views"] = mmif_data["views"][:choice]
    file_name = str(input("\nEnter the file name for the rewound mmif: "))
    with open(file_name, 'w') as json_file:
        json.dump(mmif_data, json_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process MMIF file.")
    parser.add_argument("mmif_file", help="Path to the MMIF file")
    args = parser.parse_args()

    mmif_data = read_mmif(args.mmif_file)
    choice = user_choice(mmif_data)
    process_mmif_from_user_choice(mmif_data, choice)
