# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file homekit_config.py is part of DiagralHomekit.                      #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Use Homekit objects during the configuration load."""
import asyncio
import logging
from typing import Dict

# noinspection PyPackageRequirements
from pyhap.accessory import Bridge

from diagralhomekit.diagral_config import (
    DiagralAccount,
    DiagralAlarmSystem,
    DiagralConfig,
)
from diagralhomekit.homekit import HomekitAlarm

logger = logging.getLogger(__name__)


class HomekitDiagralConfig(DiagralConfig):
    """Load a configuration with Homekit."""

    def __init__(self, bridge: Bridge):
        """init function."""
        super().__init__()
        self.bridge = bridge

    def get_account(self, login: str, password: str) -> DiagralAccount:
        """Return a Diagral account."""
        key = (login, password)
        if key not in self.accounts:
            self.accounts[key] = HomekitDiagralAccount(self, login, password)
        return self.accounts[key]


class HomekitDiagralAccount(DiagralAccount):
    """Diagral account for Homekit accessories."""

    def __init__(self, config: HomekitDiagralConfig, login: str, password: str):
        """init function."""
        super().__init__(config, login, password)
        self.accessories: Dict[int, HomekitAlarm] = {}

    def get_alarm_system(self, system_id: int, **kwargs) -> DiagralAlarmSystem:
        """Return an alarm system identified by its id."""
        alarm_system = super().get_alarm_system(system_id, **kwargs)
        if system_id not in self.accessories:
            self.accessories[system_id] = HomekitAlarm(
                alarm_system, self.config.bridge.driver
            )
            self.config.bridge.add_accessory(self.accessories[system_id])
        return self.alarm_systems[system_id]
