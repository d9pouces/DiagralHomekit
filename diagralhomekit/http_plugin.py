# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file http_plugin.py is part of DiagralHomekit.                         #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Monitor HTTP endpoints."""
import datetime
import time
import urllib.parse
from configparser import ConfigParser
from typing import List, Tuple

import requests
import systemlogger
from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_AIR_PURIFIER

from diagralhomekit.plugin import HomekitPlugin
from diagralhomekit.utils import capture_some_exception

QUALITY_UNKNOWN = 0
QUALITY_EXCELLENT = 1
QUALITY_GOOD = 2
QUALITY_FAIR = 3
QUALITY_INFERIOR = 4
QUALITY_POOR = 5

logger = systemlogger.getLogger(__name__, extra_tags={"application": "homekit"})


class SupervisionSensor(Accessory):
    """Represent a HTTP monitoring sensor."""

    category = CATEGORY_AIR_PURIFIER

    def __init__(self, plugin: HomekitPlugin, driver, server_url, name):
        """init function."""
        self.plugin = plugin
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
        prometheus_values = []
        start = time.time()
        parsed_url = urllib.parse.urlparse(self.server_url)
        try:
            r = requests.get(self.server_url, allow_redirects=False)
            ping = time.time() - start
            homekit_state = QUALITY_UNKNOWN
            status_code = r.status_code
            if status_code in {200, 401, 301, 302}:
                if ping < 1.0:
                    homekit_state = QUALITY_EXCELLENT
                elif ping < 3.0:
                    homekit_state = QUALITY_GOOD
                elif ping < 5.0:
                    homekit_state = QUALITY_FAIR
                else:
                    homekit_state = QUALITY_INFERIOR
        except Exception as e:
            ping = time.time() - start
            homekit_state = QUALITY_POOR
            capture_some_exception(e)
            status_code = 0
        prometheus_values.append((
            "homekit_http_monitoring_status", status_code,
            {"application_fqdn": parsed_url.hostname, "application": "homekit"},
        ))
        prometheus_values.append((
            "homekit_http_monitoring_state", homekit_state,
            {"application_fqdn": parsed_url.hostname, "application": "homekit"},
        ))
        prometheus_values.append((
            "homekit_http_monitoring_ping", ping,
            {"application_fqdn": parsed_url.hostname, "application": "homekit"},
        ))
        self.current_quality.set_value(homekit_state)
        logger.debug(
            f"monitoring of {self.server_url}: {homekit_state} ping={ping} status={status_code})",
            extra={"tags": {"type": "internet", "application_fqdn": parsed_url.hostname, "homekit_state": "homekit_state"}},
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
        super().load_config(parser, section)
        return config_errors

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        for data in self.urls:
            sensor = SupervisionSensor(self, bridge.driver, *data)
            self.sensors.append(sensor)
            bridge.add_accessory(sensor)

    @property
    def prometheus_metrics_type(self):
        """Return the type of Prometheus metrics."""
        return {"homekit_http_monitoring_status": "gauge",
                "homekit_http_monitoring_state": "gauge",
                "homekit_http_monitoring_ping": "gauge",
                }
