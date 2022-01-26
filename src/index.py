"""
index.py - Create a local cache of relevant manpage information.

Author: Gabriel Peery
Date: 1/25/2022
"""
import os
import subprocess
from typing import List


# TODO - move to different error file
class DependencyNotFoundError(Exception):
    """
    Raised when a dependency is detected to be missing or unreachable.
    """
    pass


# TODO - use bz2, gzip packages to open them up. For debug, we'll first
# inspect how many files are in the archives.
class ManualPage:
    """Object containing information on a manual page."""

    def __init__(self, path : str):
        """
        A manual page object constructed from analyzing the file at
        the given path.
        """
        self._paths = set()
        self.record_path(path)
        #self._extract_info(path)

    def __str__(self) -> str:
        """str(self) - Pretty printed string version"""
        return f"""Paths: {str(self._paths)}
Body:(
{self.main_text}
)"""

    def _extract_info(self, path : str):
        """Read info from file to this object."""
        with open(path, "r") as file_obj:
            self.main_text = file_obj.read()

    def record_path(self, path : str):
        """Updates object record of paths seen."""
        self._paths.add(path)


def get_manpaths(debug = False):
    """
    Returns a list of all directories where manual pages are stored.
    """
    # For debugging
    if debug:
        return ["../test/test_pages"]

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


def index(paths : List[str], verbose : bool=False):
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

    pages = dict() # Collection of ManualPage objects
    for path in paths:
        # Walk each tree
        for dirpath, _, files in os.walk(path, followlinks=True):
            # Examine files
            for file_iter in files:
                full_path = os.path.join(dirpath, file_iter)
                real_path = os.path.realpath(full_path)
                # Check if already seen
                if real_path not in pages:
                    # First time analysis
                    page = ManualPage(real_path)
                    pages[real_path] = page

                    if verbose:
                        print(real_path.center(term_size, "-"))
                        #print(page)
                else:
                    # nth time analysis.
                    pages[real_path].record_path(full_path)


def main():
    # TODO - accept command line arguments
    paths = get_manpaths()
    index(paths, True)


if __name__ == "__main__":
    main()

