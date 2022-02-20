"""
index.py - Create a local cache of relevant manpage information.

Author: Gabriel Peery
Date: 1/25/2022
"""
import argparse
import bz2
import enum
from errors import *
import gzip
import json
import os
import subprocess
from typing import List, Tuple


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

    # Maximum amount of chars to read in a block from decompressed text
    # TODO - find fast value of this
    BLOCK_SIZE = 1024

    def __init__(self, path : str):
        """
        A manual page object constructed from analyzing the file at the 
        given path. Will decompress if needed.

        Note that the path should be the real path.
        """
        self._paths = set()
        self._title = None
        self._sections = None
        self._last_modification_time = None
        self._need_to_extract = True

        self.record_path(path)

    def __str__(self) -> str:
        """str(self) - Pretty printed string version"""
        return f"""Paths: {str(self._paths)}
Title:{self._title}
Modification:{self._last_modification_time}
"""

    def _extract_info(self, path : str):
        """Read info from file to this object."""
        # Metadata
        self._last_modification_time = os.path.getmtime(path)

        # Information that requires reading the file
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

            # Parse through file
            self._parse(zipped_file);

            # Close wrapper file object as appropriate
            if compress_t == CompressT.GZIP or compress_t == CompressT.BZIP2:
                zipped_file.close()

    def _parse(self, zipped_file):
        """Set local variables to store relevant information on page."""
        # Let groff create the plaintext
        try:
            groff_result = subprocess.run(
                ["groff", "-Tascii", "-man"], # Internationalization ?
                input=zipped_file.read(),
                capture_output=True
            )
        except FileNotFoundError:
            raise DependencyNotFoundError("Could not find 'groff' to run.")

        # Get decoded full text as list of lines
        full_text = groff_result.stdout.decode("ascii", "replace").splitlines()

        if len(full_text) == 0:
            # Likely caused by another file being sourced into this one
            # Still need to extract, so don't change that
            return

        # Phase 1: Retrieve title
        line_idx = 0
        while full_text[line_idx].strip() == '':
            line_idx += 1
        self._title = full_text[line_idx].strip().split()[0].split('(')[0]

        #
        # Phase 2: Read through entire file looking for sections. Keep
        # the ones considered significant
        #
        self._sections = dict()

        current_section = None # Write into this section
        for line in full_text[1:]:
            # Skip empty lines
            if line == '':
                continue

            # Section titles are uppercase and the line describing them
            # does not start with a space
            if (not line[0].isspace()) and line[0].isupper():
                current_section = None
                isolated_section_name = line[0].split()[0]
                if is_desireable_section(isolated_section_name):
                    current_section = isolate_section_name
                    self._sections[isolate_section_name] = ""
                    continue # Don't write name itself

            # Write lines to relevant section
            if current_section is not None:
                self._sections[current_section] += '\n' + line

        # No need to extract any longer
        self._need_to_extract = False

    def record_path(self, path : str):
        """Updates object record of paths seen."""
        self._paths.add(path)
        if self._need_to_extract:
            self._extract_info(path)

    def get_save_info(self) -> Tuple[str, dict]:
        """Returns the title and dictionary of things worth caching."""
        return self._title, {
            "paths" : list(self._paths),
            "modification" : self._last_modification_time
        }


_GOOD_SECTIONS = None
SECTION_FILE = None


def is_desireable_section(section_name : str) -> bool:
    """Returns True if section_name is listed in SECTION_FILE."""
    global _GOOD_SECTIONS, SECTION_FILE

    # Case need to generate
    if _GOOD_SECTIONS is None:
        _GOOD_SECTIONS = set()

        # Determine where the file is
        if SECTION_FILE is None:
            SECTION_FILE = os.path.join(os.path.dirname(__file__),
                    "../config/.sections")

        try:
            with open(SECTION_FILE, "r") as config_file:
                for line in config_file:
                    _GOOD_SECTIONS.add(line.upper().strip())
        except FileNotFoundError:
            raise FileNotFoundError(f"{SECTION_FILE} file is missing!")

    # Then check inside
    return section_name in _GOOD_SECTIONS


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

                    page = ManualPage(real_path)
                    pages[real_path] = page

                    if verbose:
                        print(page)
                else:
                    # nth time analysis.
                    pages[real_path].record_path(full_path)
    print("...done.")

    # Save python objects
    dump_str = json.dumps({
        title : data for title, data in map(
            ManualPage.get_save_info, pages.values()
        )
    }) + "\n"

    # Default cache file
    if cache_file is None:
        cache_file = os.path.join(os.path.dirname(__file__),
                "../cache/discoverability_cache")

    print("Writing to cache...")
    with bz2.open(cache_file, "wb") as cache:
        cache.write(bytes(dump_str, 'ascii'))
    print("...done.")


def main():
    global SECTION_FILE
    
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
    SECTION_FILE = args.sections

    # Retrieve information
    paths = get_manpaths()
    index(paths, args.v, args.cache)


if __name__ == "__main__":
    main()

