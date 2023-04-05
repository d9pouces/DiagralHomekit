# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file utils.py is part of DiagralHomekit.                               #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Some utility functions."""
import re
import time

from requests.exceptions import ConnectionError, ConnectTimeout, SSLError
from sentry_sdk import capture_exception
from urllib3.exceptions import NewConnectionError

BASE_AID = 1_970_000_000_000


def sleep():
    """Sleep for a few seconds."""
    time.sleep(5)


def capture_some_exception(e):
    """Silently discards some network exceptions."""
    if isinstance(
        e,
        (
            NewConnectionError,
            AssertionError,
            ValueError,
            SSLError,
            ConnectionError,
            ConnectTimeout,
        ),
    ):
        return
    return capture_exception(e)


class RegexValidator:
    """Check if the value matches the given regexp."""

    def __init__(self, pattern: str):
        """init function."""
        self.regex = re.compile(pattern)

    def __call__(self, value: str):
        """Check if the value matches the given regexp."""
        if not self.regex.match(value):
            raise ValueError(f"Invalid value {value}")
        return value


def bool_validator(value: str) -> bool:
    """Convert a simple text to a boolean value.

    >>> bool_validator("1")
    True

    >>> bool_validator("false")
    False

    :param value:
    :return:
    """
    return value and value.lower() in {"yes", "true", "1", "on"}
