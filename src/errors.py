"""
errors.py - Exceptions that may be raised by discoverability

Author: Gabriel Peery
Date: 2/5/2022
"""
class DependencyNotFoundError(Exception):
    """
    Raised when a dependency is detected to be missing or unreachable.
    """
    pass


class NoDataReadError(Exception):
    """
    Raised when no data was read from a manual page, but data is
    requested.
    """
    pass

