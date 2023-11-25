# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file http_plugin.py is part of DiagralHomekit.                         #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Monitor HTTP endpoints."""
import datetime
import time
from configparser import ConfigParser
from typing import List, Tuple

import requests
import systemlogger
from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_AIR_PURIFIER

from diagralhomekit.plugin import HomekitPlugin
from diagralhomekit.utils import capture_some_exception

logger = systemlogger.getLogger(__name__)


class SupervisionSensor(Accessory):
    """Represent a HTTP monitoring sensor."""

    category = CATEGORY_AIR_PURIFIER

    def __init__(self, driver, server_url, name):
        """init function."""
        self.server_url = server_url
        aid = hash(server_url)
        super().__init__(driver, name, aid=aid)
        info_service = self.get_service("AccessoryInformation")
        for char_name, value in (
            ("Identify", False),
            ("Manufacturer", "19pouces"),
            ("Model", "HTTP monitoring"),
            ("SerialNumber", datetime.datetime.now().strftime("%Y%m%d%H%M%S")),
            ("Name", name),
        ):
            characteristic = info_service.get_characteristic(char_name)
            characteristic.set_value(value)

        service = self.add_preload_service("AirQualitySensor", chars=[])
        self.current_quality = service.get_characteristic("AirQuality")

    @Accessory.run_at_interval(60)
    def run(self):
        """Run at regular interval for monitoring the given URL."""
        # noinspection PyBroadException
        try:
            start = time.time()
            r = requests.get(self.server_url, allow_redirects=False)
            end = time.time()
            value = 5
            if r.status_code in {200, 401, 301, 302}:
                delta = end - start
                if delta < 1.0:
                    value = 1
                elif delta < 3.0:
                    value = 2
                if delta < 5.0:
                    value = 3
                else:
                    value = 4
        except Exception as e:
            value = 5
            capture_some_exception(e)
        self.current_quality.set_value(value)
        logger.debug(
            f"monitoring of {self.server_url}: {value}",
            extra={"tags": {"type": "internet"}},
        )


class HttpMonitoringPlugin(HomekitPlugin):
    """Plugin for plex servers."""

    config_prefix = "internet"
    plex_requirements = {
        "url": str,
        "name": str,
    }

    def __init__(self, config):
        """init function."""
        super().__init__(config)
        self.urls: List[Tuple[str, str]] = []
        self.sensors: List[SupervisionSensor] = []

    def load_config(self, parser: ConfigParser, section):
        """Load a configuration section."""
        logger.debug(f"loading {section}")
        config_errors = []
        server_url = parser.get(section, "url", fallback=None)
        name = parser.get(section, "name", fallback=None)
        if name is None:
            msg = f"Invalid option name in section {section}."
            config_errors.append(msg)
            logger.fatal(msg)
        if server_url is None:
            msg = f"Invalid option url in section {section}."
            config_errors.append(msg)
            logger.fatal(msg)
        self.urls.append((server_url, name))
        logger.info(
            f"Configuration for monitoring {name} {server_url} added.",
            extra={"tags": {"type": "internet"}},
        )
        return config_errors

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        for data in self.urls:
            sensor = SupervisionSensor(bridge.driver, *data)
            self.sensors.append(sensor)
            bridge.add_accessory(sensor)
