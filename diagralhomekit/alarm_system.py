# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file alarm_system.py is part of DiagralHomekit.                        #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Define a generic alarm system."""
import logging
from typing import Set

logger = logging.getLogger(__name__)


class AlarmSystem:
    """Generic alarm system."""

    def __init__(self, name: str):
        """init function."""
        self.name = name
        self._active_groups: Set[int] = set()
        self.is_triggered = False
        self.trigger_date = None
        self.status_fault = False

    def extra_log_data(self, **kwargs):
        """Extra data for logging events."""
        return {
            "tags": {
                "identifier": str(self.identifier),
                "name": self.name,
                "type": "system",
                **kwargs,
            }
        }

    @property
    def identifier(self) -> int:
        """return a unique identifier."""
        raise NotImplementedError

    @property
    def serial_number(self) -> str:
        """return the serial number of this system."""
        raise NotImplementedError

    def __str__(self):
        """Represent the object."""
        return f"{self.__class__.__name__}('{self.name}')"

    def __repr__(self):
        """Represent the object."""
        return f"{self.__class__.__name__}('{self.name}')"

    def set_active_groups(self, groups: Set[int]):
        """set the new current active groups."""
        self._active_groups = groups
        if not groups:
            self.is_triggered = False

    def get_active_groups(self) -> Set[int]:
        """return the currently active groups."""
        return self._active_groups

    def get_stay_groups(self) -> Set[int]:
        """return the selected groups for stay configuration."""
        raise NotImplementedError

    def get_night_groups(self) -> Set[int]:
        """return the selected groups for night configuration."""
        raise NotImplementedError

    def activate_groups(self, groups: Set[int]):
        """activate the selected groups."""
        raise NotImplementedError
