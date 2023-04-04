import time

import random

import re

from sentry_sdk import capture_exception
from urllib3.exceptions import NewConnectionError
from requests.exceptions import SSLError, ConnectionError, ConnectTimeout

BASE_AID = 1_970_000_000_000


def sleep():
    time.sleep(random.randint(1, 5))


def capture_some_exception(e):
    if isinstance(e, (NewConnectionError, AssertionError, ValueError, SSLError, ConnectionError, ConnectTimeout)):
        return
    return capture_exception(e)


class RegexValidator:
    def __init__(self, pattern: str):
        self.regex = re.compile(pattern)

    def __call__(self, value: str):
        if not self.regex.match(value):
            raise ValueError(f"Invalid value {value}")
        return value
