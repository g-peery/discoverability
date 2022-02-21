"""
Functions and objects associated with reading manual pages, coordinating
their use for searching.

Author: Gabriel Peery
Date: 2/21/2022
"""
import bz2
import enum
from errors import *
import gzip
import os
import re
import subprocess
from typing import List, Tuple, Union


class _CompressT(enum.Enum):
    NONE = enum.auto()
    GZIP = enum.auto()
    BZIP2 = enum.auto()


class ManualPage:
    """Object containing information on a manual page."""

    # Magic bytes
    _TYPE_LOOKUP = {
        b"\x1f\x8b" : _CompressT.GZIP,
        b"BZ" : _CompressT.BZIP2
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
                _CompressT.NONE
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
            if compress_t == _CompressT.GZIP:
                zipped_file = gzip.GzipFile(fileobj=file_obj)
            elif compress_t == _CompressT.BZIP2:
                zipped_file = bz2.BZ2File(file_obj)
            else:
                zipped_file = file_obj

            # Parse through file
            self._parse(zipped_file);

            # Close wrapper file object as appropriate
            if compress_t == _CompressT.GZIP or compress_t == _CompressT.BZIP2:
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
        # Get rid of bold/italic weirdness
        full_text = _degrotty(
            groff_result.stdout.decode("ascii", "ignore").splitlines()
        )

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
            if line == '' or line.isspace():
                continue

            if _is_section_title(line):
                current_section = None # Not in old section any more
                isolated_section_name = line.strip()
                if _is_desireable_section(isolated_section_name):
                    current_section = isolated_section_name
                    self._sections[isolated_section_name] = ""
                    continue # Don't write name itself

            # Write lines to relevant section
            if current_section is not None:
                self._sections[current_section] += line.strip() + " "

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
            "modification" : self._last_modification_time,
            "sections" : self._sections
        }


def _is_section_title(line : str) -> bool:
    """
    Given an isolated line as ouput by groff, returns True if it is a 
    section title of a manpage.
    """
    return (
        line.isupper() # Uppercase
        and (not line[0].isspace()) # First part of line
        and all([tok.isalpha() for tok in line.split()]) # Alphabet only
        )


def _degrotty(full_text : List[str]) -> List[str]:
    """
    Given a list of lines as output by groff, replaces special sequences
    for bold characters and italic characters with their single
    character replacements in the output list of strings.
    """
    undo_bold = lambda line : re.sub("(.)\x08\\1", r"\1", line)
    undo_italics = lambda line : re.sub("_\x08(.)", r"\1", line)
    return [undo_italics(undo_bold(line)) for line in full_text]


_GOOD_SECTIONS = None
_SECTION_FILE = None


def _is_desireable_section(section_name : str) -> bool:
    """Returns True if section_name is listed in _SECTION_FILE."""
    global _GOOD_SECTIONS, _SECTION_FILE

    # Case need to generate
    if _GOOD_SECTIONS is None:
        _GOOD_SECTIONS = set()

        # Determine where the file is
        if _SECTION_FILE is None:
            _SECTION_FILE = os.path.join(os.path.dirname(__file__),
                    "../config/.sections")

        try:
            with open(_SECTION_FILE, "r") as config_file:
                for line in config_file:
                    _GOOD_SECTIONS.add(line.upper().strip())
        except FileNotFoundError:
            raise FileNotFoundError(f"{_SECTION_FILE} file is missing!")

    # Then check inside
    return section_name in _GOOD_SECTIONS


def set_section_file(new_section_file_name : Union[str, None]):
    """
    Sets the name of the file to get section names from. May also supply
    None, in which case variables will simply be reset and sections will
    be read the next time they are needed.
    """
    # Check type
    if type(new_section_file_name) not in [str, type(None)]:
        raise TypeError("Section file name must be a string.")
    # Reset variables
    _GOOD_SECTIONS = None
    _SECTION_FILE = new_section_file_name
    
