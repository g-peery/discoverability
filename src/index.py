"""
index.py - Create a local cache of relevant manpage information.

Author: Gabriel Peery
Date: 1/25/2022
"""
# BIG TODO - need way to be sure that files are manual pages
import bz2
import enum
import gzip
import locale
import os
import subprocess
from typing import List


# TODO - move to different error file
class DependencyNotFoundError(Exception):
    """
    Raised when a dependency is detected to be missing or unreachable.
    """
    pass


class CompressT(enum.Enum):
    NONE = enum.auto()
    GZIP = enum.auto()
    BZIP2 = enum.auto()


class ManualPage:
    """Object containing information on a manual page."""

    # Magic bytes
    _TYPE_LOOKUP = {
    b"\x1f\x8b" : CompressT.GZIP,
    b"BZ" : CompressT.BZIP2
    }

    def __init__(self, path : str, locale : str):
        """
        A manual page object constructed from analyzing the file at the 
        given path. Will decompress if needed, then handle according to 
        provided locale.
        """
        self._paths = set()
        self._locale = locale

        self.record_path(path)
        self._extract_info(path)

    def __str__(self) -> str:
        """str(self) - Pretty printed string version"""
        return f"""Paths: {str(self._paths)}
Title:{self._title}"""

    def _extract_info(self, path : str):
        """Read info from file to this object."""
        with open(path, "rb") as file_obj:
            #
            # Determine File Type
            # 
            # Check for magic characters
            compress_t = self._TYPE_LOOKUP.setdefault(
                file_obj.read(2),
                CompressT.NONE
            )

            # Go back to start
            if file_obj.seekable():
                file_obj.seek(0)
            else:
                file_obj.close()
                file_obj = open(path, "rb")

            # 
            # Extract information
            #
            # Get appropriate file object
            if compress_t == CompressT.GZIP:
                zipped_file = gzip.GzipFile(fileobj=file_obj)
            elif compress_t == CompressT.BZIP2:
                zipped_file = bz2.BZ2File(file_obj)
            else:
                zipped_file = file_obj

            # Read plaintext
            full_text = zipped_file.read().decode(self._locale, "replace")

            # Close wrapper file object as appropriate
            if compress_t == CompressT.GZIP or compress_t == CompressT.BZIP2:
                zipped_file.close()

        # Finally, parse through file
        self._parse(full_text)

    def _parse(self, full_text : str):
        """Set local variables to store relevant information on page."""
        lines = full_text.splitlines()
        lines_iterator = iter(lines)

        # Find man page title
        self._title = None
        try:
            while self._title is None:
                line = next(lines_iterator)
                if line[:3] == ".TH":
                    # This is the title line. Find the title field.
                    stop_char = ' ' # Default space
                    start_pos = 4
                    if line[4] == '"':
                        # Case go in between the quotes
                        stop_char = '"'
                        start_pos += 1

                    # Build title character by character
                    self._title = ""
                    for idx, c in enumerate(line[start_pos:]):
                        if c == stop_char:
                            break
                        if c == '\\' and not line[start_pos + idx - 1] == '\\':
                            continue
                        self._title += c
                        
        except StopIteration:
            # TODO - throw an error that this is not a manpage.
            pass

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
    # This will be needed to parse pages
    encoding = locale.getdefaultlocale()[1]

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
                    if verbose:
                        print(real_path.center(term_size, "-"))

                    page = ManualPage(real_path, encoding)
                    pages[real_path] = page

                    if verbose:
                        print(page)
                else:
                    # nth time analysis.
                    pages[real_path].record_path(full_path)


def main():
    # TODO - accept command line arguments
    paths = get_manpaths()
    index(paths, True)


if __name__ == "__main__":
    main()

