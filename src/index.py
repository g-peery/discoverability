"""
index.py - Create a local cache of relevant manpage information.

Author: Gabriel Peery
Date: 1/25/2022
"""
import argparse
import bz2
from errors import *
import json
import os
import page_interface as pi
import subprocess
from typing import List


def get_manpaths(debug = False):
    """
    Returns a list of all directories where manual pages are stored.

    If debug is True, then looks in the test folder of the project for
    pages.
    """
    # For debugging
    if debug:
        test_path = os.path.join(os.path.abspath(""),
                "../test/test_pages")
        return [test_path]

    #
    # Real analysis
    #
    # Use manpath program to get what man will use
    try:
        manpath_result = subprocess.run(
            "manpath",
            capture_output=True, 
            text=True
        )
        return manpath_result.stdout.strip().split(":")
    except FileNotFoundError:
        raise DependencyNotFoundError("Could not find 'manpath' to run.")


def index(paths : List[str], verbose : bool, cache_file : str):
    """
    For each path in the list of strings, searches for manual pages.
    If verbose, then prints useful debug information.

    Note that bad things will happen if there are link loops.
    """
    # Prepare pretty printing
    if verbose:
        try:
            term_size = os.get_terminal_size().columns
        except OSError:
            term_size = 80

    print("Walking manpath...")
    # Get Python objects
    pages = dict() # Collection of ManualPage objects, keys are names
    for path in paths:
        # Walk each tree
        for dirpath, _, files in os.walk(path, followlinks=True):
            # Examine files
            for file_iter in files:
                # Extract path information
                full_path = os.path.join(dirpath, file_iter)
                real_path = os.path.realpath(full_path)
                try:
                    name = pi.ManualPage.get_name(real_path)
                except ValueError:
                    # Happens when wasn't a manual page, just ignore
                    if verbose:
                        print(("Skipped " + real_path).center(term_size, "%"))
                    continue

                # Check if already seen
                if name not in pages:
                    # First time analysis
                    if verbose:
                        print(real_path.center(term_size, "-"))

                    page = pi.ManualPage(real_path)
                    pages[name] = page

                    if verbose:
                        print(page)
                else:
                    # nth time analysis.
                    pages[name].record_path(full_path)
    print("...done.")

    # Save python objects
    print("Writing to cache...")
    # First, construct the dictionary
    dict_to_dump = dict()
    for name, page in pages.items():
        try:
            title, data = pi.ManualPage.get_save_info(page)
            dict_to_dump[title] = data
        except NoDataReadError:
            # Happens when empty, just ignore
            if verbose:
                print(f"No data was read from {name}")
            pass

    # Convert to string
    dump_str = json.dumps(dict_to_dump) + "\n"

    # Default cache file
    if cache_file is None:
        cache_file = os.path.join(os.path.abspath(""),
                "../cache/discoverability_cache")

    with bz2.open(cache_file, "wb") as cache:
        cache.write(bytes(dump_str, 'ascii'))
    print("...done.")


def main():
    # Deal with command line arguments
    parser = argparse.ArgumentParser(description="Create a cache of "
            "text information from manpage files.")
    parser.add_argument("-v", action='store_const', const=True, default=False,
            help="Verbose output")
    parser.add_argument("-c", "--cache", metavar="CACHE", type=str,
            default=None, help="Destination cache file")
    parser.add_argument("-s", "--sections", metavar="SECTIONS", type=str,
            default=None, help="Source sections to look for in pages")
    args = parser.parse_args()
    pi.set_section_file(args.sections)

    # Retrieve information
    paths = get_manpaths()
    index(paths, args.v, args.cache)


if __name__ == "__main__":
    main()

