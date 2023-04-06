# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file utils.py is part of DiagralHomekit.                               #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Some utility functions."""
import re
import unicodedata

from requests.exceptions import ConnectionError, ConnectTimeout, SSLError
from sentry_sdk import capture_exception
from urllib3.exceptions import NewConnectionError

BASE_AID = 1_970_000_000_000


def slugify(value: str) -> str:
    """Remove special chars from strings.

    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single underscores. Remove characters that aren't alphanumerics or
    underscores. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.

    >>> slugify('* alarm test')
    'alarm_test'
    """
    value = str(value)
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-_\s]+", "_", value).strip("-_")


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
