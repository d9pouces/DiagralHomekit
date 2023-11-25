# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file plex.py is part of DiagralHomekit.                                #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Plex plugin, to add a OccupancySensor for each player."""
import time
from configparser import ConfigParser
from multiprocessing.pool import ThreadPool
from typing import Dict, List, Optional, Tuple

import requests
import systemlogger
from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_SENSOR

from diagralhomekit.plugin import HomekitPlugin
from diagralhomekit.utils import RegexValidator, str_or_none

logger = systemlogger.getLogger(__name__)


class PlexActivitySensor(Accessory):
    """Homekit occupancy sensor, detect an activity when the player is active."""

    category = CATEGORY_SENSOR

    def __init__(
        self,
        driver,
        account=None,
        player_name: str = None,
        player_device=None,
        player_product=None,
        player_title=None,
        player_address=None,
    ):
        """init function."""
        self.selected_player_device = player_device
        self.selected_player_product = player_product
        self.selected_player_title = player_title
        self.selected_player_address = player_address
        self.plex_account: PlexAccount = account
        aid = hash(str(player_name))
        self.player_name = player_name
        super().__init__(driver, player_name, aid=aid)

        service = self.add_preload_service("OccupancySensor", chars=["StatusFault"])
        self.occupancy_detected = service.get_characteristic("OccupancyDetected")
        self.status_fault = service.get_characteristic("StatusFault")
        self.is_active = False
        self.previous_state = False
        self.is_loaded = False

    def set_characteristics(self):
        """Fetch Plex info."""
        if self.is_loaded:
            return
        try:
            info_service = self.get_service("AccessoryInformation")
            server_info = self.plex_account.get_server_info()
            for char_name, value in (
                ("Identify", False),
                ("Manufacturer", "Plex.tv"),
                ("Model", "Plex"),
                ("Name", f"{self.player_name}"),
                ("SerialNumber", server_info["host"]),
                ("FirmwareRevision", server_info["version"]),
            ):
                characteristic = info_service.get_characteristic(char_name)
                characteristic.set_value(value)
            self.is_loaded = True
        except Exception as e:
            logger.exception(e)


class PlexAccount:
    """Represent an account on a plex server."""

    def __init__(self, config, server_url: str, server_token: str):
        """init function."""
        self.config = config
        self.server_url = server_url
        self.server_token = server_token
        self.plex_sensors_data: List[Dict[str, Optional[str]]] = []
        self.plex_sensors: List[PlexActivitySensor] = []
        self.is_running = True

    def __str__(self):
        """Return a string."""
        return f"PlexAccount('{self.server_url})"

    def get_api_result(self, endpoint: str):
        """Request the plex server API."""
        r = requests.get(
            self.server_url + endpoint,
            headers={"Accept": "application/json", "X-Plex-Token": self.server_token},
        )
        return r.json()["MediaContainer"]

    def extra_log_data(self, **kwargs):
        """Extra data for logging events."""
        return {"tags": {"identifier": self.server_url, "type": "plex", **kwargs}}

    def sleep_while_run(self, interval_in_s: int):
        """Sleep for the given interval if active."""
        for __ in range(interval_in_s * 10):
            if not self.is_running:
                return
            time.sleep(0.1)

    def run(self):
        """Continuously update the systems and looks for alarms."""
        extra = self.extra_log_data()
        while self.is_running:
            logger.debug(f"Update Plex data for {self.server_url}", extra=extra)
            try:
                self.update_all_sensors()
            except Exception as e:
                logger.exception(e)
                for sensor in self.plex_sensors:
                    sensor.status_fault.set_value(1)
            self.sleep_while_run(10)

    def get_server_info(self):
        """Return main server data."""
        server_info = self.get_api_result("servers")["Server"][0]
        return server_info

    def update_all_sensors(self):
        """Update all Plex sensors."""
        r = self.get_api_result("status/sessions")
        sessions = r.get("Metadata", [])
        for sensor in self.plex_sensors:
            sensor.previous_state = sensor.is_active
            sensor.is_active = False
        for session in sessions:
            player = session["Player"]
            if player["state"] != "playing":
                continue
            for sensor in self.plex_sensors:
                if player["title"] == sensor.selected_player_title:
                    sensor.is_active = True
                elif player["product"] == sensor.selected_player_product:
                    sensor.is_active = True
                elif player["device"] == sensor.selected_player_device:
                    sensor.is_active = True
                elif player["address"] == sensor.selected_player_address:
                    sensor.is_active = True
        for sensor in self.plex_sensors:
            sensor.set_characteristics()
            sensor.occupancy_detected.set_value(1 if sensor.is_active else 0)
            if sensor.is_active != sensor.previous_state:
                logger.info(
                    f"State changed for {sensor.display_name}: {sensor.is_active}"
                )
            sensor.status_fault.set_value(0)


class PlexHomekitPlugin(HomekitPlugin):
    """Plugin for plex servers."""

    config_prefix = "plex"
    plex_requirements = {
        "server_url": str,
        "server_token": str,
        "player_device": str_or_none,
        "player_product": str_or_none,
        "player_title": str_or_none,
        "player_name": RegexValidator(".+"),
        "player_address": str_or_none,
    }

    def __init__(self, config):
        """init function."""
        super().__init__(config)
        self.plex_accounts: [Tuple[str, str], PlexAccount] = {}
        self.thread_pool = None

    def get_account(self, server_url: str, server_token: str) -> PlexAccount:
        """Get an account identified by the login and the password."""
        key = (server_url, server_token)
        if key not in self.plex_accounts:
            self.plex_accounts[key] = PlexAccount(self.config, *key)
        return self.plex_accounts[key]

    def load_config(self, parser: ConfigParser, section):
        """Load a configuration section."""
        """Load a configuration section."""
        logger.debug(f"loading {section}")
        config_errors = []
        kwargs = {}
        for kwarg, checker in self.plex_requirements.items():
            raw_value = parser.get(section, kwarg, fallback=None)
            if raw_value is not None:
                try:
                    kwargs[kwarg] = checker(raw_value)
                except ValueError:
                    msg = f"Invalid option {kwarg} in section {section}."
                    config_errors.append(msg)
                    logger.fatal(msg)
                    continue
        if not config_errors:
            key = kwargs.pop("server_url"), kwargs.pop("server_token")
            account = self.get_account(*key)
            account.plex_sensors_data.append(kwargs)
            logger.info(
                f"Configuration for Plex player {kwargs} added.",
                extra=account.extra_log_data(),
            )
        return config_errors

    def run_all(self):
        """Run all daemons in separate threads."""
        if self.plex_accounts:
            self.thread_pool = ThreadPool(len(self.plex_accounts))
            for account in self.plex_accounts.values():
                self.thread_pool.apply_async(account.run)

    def stop_all(self):
        """Stop all accounts."""
        for account in self.plex_accounts.values():
            account.is_running = False

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        for account in self.plex_accounts.values():
            for data in account.plex_sensors_data:
                sensor = PlexActivitySensor(bridge.driver, account, **data)
                account.plex_sensors.append(sensor)
                bridge.add_accessory(sensor)
