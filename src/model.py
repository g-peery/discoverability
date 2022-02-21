"""
Objects and methods for interfacing with search models.

Author: Gabriel Peery
Date: 2/21/2022
"""


class Model:
    """Contains info about search model and methods to interact."""

    _GOOD_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def __init__(self):
        """Constructor - TODO"""
        pass

    def preprocess(self, text : str) -> str:
        """Prepare string for tokenization and other steps."""
        # Groff sometimes splits words like this
        text = text.replace("- ", "")
        # Most characters should be replaced by space, but not all
        replace_policy = lambda c : '' if c == "'" else ' '
        return ' '.join((
            ''.join([
                c if c in self._GOOD_CHARS else replace_policy(c) for c in text
            ])
        ).split()).lower()

