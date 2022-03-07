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
from hashlib import sha1
import model
import os
import re
import subprocess
from typing import List, Tuple, Union


class _CompressT(enum.Enum):
    NONE = enum.auto()
    GZIP = enum.auto()
    BZIP2 = enum.auto()


# TODO - separate caching behavior from training
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

    @staticmethod
    def _name_valid(split_name : List[str]) -> bool:
        """
        Returns true if name looks like it could be to a manual page.
        """
        return split_name[-2].isnumeric() and len(split_name) >= 3

    @staticmethod
    def _get_name_and_section(path : str) -> Tuple[str, int]:
        """
        Retrieves the name and section of the manual page at path.
        Raises ValueError if can't read it.
        """
        split_name = path.split(os.path.sep)[-1].split(".")

        # Plaintext case:
        if split_name[-1].isnumeric():
            return ".".join(split_name[:-1]), int(split_name[-1])

        # Else, it is some other file, we can check further:
        # Perform weak check for compressed files
        if not ManualPage._name_valid(split_name):
            raise ValueError(f"{path} doesn't look like a manual page.")

        return ".".join(split_name[:-2]), int(split_name[-2])

    @staticmethod
    def get_name(path : str) -> str:
        """
        From a path to a manual page, retrieves the title of the manual
        page, if it can be recognized. Raises a value error if can't
        read.
        """
        name, section = ManualPage._get_name_and_section(path)
        return name + f" ({section})"

    def __init__(self, path : str):
        """
        A manual page object constructed from analyzing the file at the 
        given path. Will decompress if needed.

        Note that the path should be the real path. If can't be read,
        will raise an error.
        """
        self._paths = [ ]
        # Note: following may throw and error
        self._title, self._section_number = ManualPage._get_name_and_section(
            path
        )
        self._sections = dict()
        self._last_modification_time = 0 # Sentinel 
        self._hashes = set()
        self._model = get_model()

        self.record_path(path)

    def __str__(self) -> str:
        """str(self) - Pretty printed string version"""
        return f"""Paths: {str(self._paths)}
Title:{self._title}
Section:{self._section_number}
Modification:{self._last_modification_time}
"""

    def _extract_info(self, path : str):
        """Read info from file to this object."""
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
            self._parse(zipped_file, path);

            # Close wrapper file object as appropriate
            if compress_t == _CompressT.GZIP or compress_t == _CompressT.BZIP2:
                zipped_file.close()

    def _parse(self, zipped_file, path : str):
        """Set local variables to store relevant information on page."""
        # Let groff create the plaintext
        try:
            groff_result = subprocess.run(
                ["groff", "-Tascii", "-man"], # Internationalization ?
                input=zipped_file.read(),
                capture_output=True,
                cwd=os.path.dirname(path)
            )
        except FileNotFoundError:
            raise DependencyNotFoundError("Could not find 'groff' to run.")

        # First, check if we need to record
        hasher = sha1()
        this_hash = hasher.update(groff_result.stdout)
        if this_hash in self._hashes:
            # Very likely already seen, don't continue
            return
        # If here, definitely haven't seen yet.
        self._hashes.add(this_hash)

        # Get decoded full text as list of lines
        # Get rid of bold/italic weirdness
        full_text = _degrotty(
            groff_result.stdout.decode("ascii", "ignore").splitlines()
        )

        if len(full_text) == 0:
            # Likely caused by another file being sourced into this one
            # Still need to extract, so don't change that
            return

        # Phase 1: Go past title
        line_idx = 0
        while full_text[line_idx].strip() == '':
            line_idx += 1

        #
        # Phase 2: Read through entire file looking for sections. Keep
        # the ones considered significant
        #
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
                    if isolated_section_name in self._sections:
                        self._sections[isolated_section_name] += " "
                    else:
                        self._sections[isolated_section_name] = ""
                    continue # Don't write name itself

            # Write lines to relevant section
            if current_section is not None:
                self._sections[current_section] += line.strip() + " "

    def _clean_data(self):
        """
        Puts section data through preprocessing. Returns true if there
        were sections to be found.
        """
        if len(self._sections) == 0:
            return False
        for section in self._sections:
            self._sections[section] = self._model.preprocess(
                self._sections[section]
            )
        return True

    def record_path(self, path : str):
        """Updates object record of paths seen."""
        # Record that this was called
        self._paths.append(path)
        # See if need to update time
        self_last_modification_time = max(
            os.path.getmtime(path), self._last_modification_time
        )
        # Extract any new information
        self._extract_info(path)

    def get_save_info(self) -> Tuple[str, dict]:
        """Returns the title and dictionary of things worth caching."""
        # Clean up data first
        # This also acts as a good test of whether any sections were
        # found. By the manpage standard, there must at least be a NAME
        # field.
        if not self._clean_data():
            raise NoDataReadError(f"No data was read for {self._title}.")

        # Put in a nice format
        compound_title = self._title + f" ({self._section_number})"
        return compound_title, {
            "title" : self._title,
            "section" : self._section_number,
            "paths" : self._paths,
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
            _SECTION_FILE = os.path.join(os.path.abspath(""),
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
    global _GOOD_SECTIONS, _SECTION_FILE

    # Check type
    if type(new_section_file_name) not in [str, type(None)]:
        raise TypeError("Section file name must be a string.")
    # Reset variables
    _GOOD_SECTIONS = None
    _SECTION_FILE = new_section_file_name


_MODEL = None


def set_model(new_model : model.Model):
    """Sets the model for the interface to use."""
    global _MODEL

    # Check type
    if type(new_model) != model.Model:
        raise TypeError("Model must be a model.Model instance")
    # Reset variables
    _MODEL = new_model


def get_model() -> model.Model:
    """Retrieves the model the interface is using, or sets default."""
    global _MODEL

    if _MODEL is None:
        # Set to default
        _MODEL = model.Model() # TODO - will need to take from file

    return _MODEL

