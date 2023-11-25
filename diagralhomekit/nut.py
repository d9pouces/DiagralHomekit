# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file nut.py is part of DiagralHomekit.                                 #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""UPS sensor fetching data from the local NUT client."""
from configparser import ConfigParser
from typing import List

import systemlogger
from nut2 import PyNUTClient, PyNUTError

# noinspection PyPackageRequirements
from pyhap.accessory import Accessory

# noinspection PyPackageRequirements
from pyhap.const import CATEGORY_SENSOR

from diagralhomekit.plugin import HomekitPlugin

logger = systemlogger.getLogger(__name__)


class UPSSensor(Accessory):
    """UPS sensor., compatible with the NUT server."""

    category = CATEGORY_SENSOR

    def __init__(self, driver, ups_name, ups_verbose_name, ups_data):
        """init function."""
        serial = ups_data["ups.serial"]
        aid = hash(f"{serial}")
        super().__init__(driver, ups_verbose_name, aid=aid)
        info_service = self.get_service("AccessoryInformation")
        for char_name, value in (
            ("Identify", False),
            ("Manufacturer", ups_data["ups.mfr"]),
            ("Model", ups_data["ups.model"]),
            ("Name", ups_verbose_name),
            ("SerialNumber", serial),
            ("FirmwareRevision", str(ups_data["ups.firmware"])),
        ):
            characteristic = info_service.get_characteristic(char_name)
            characteristic.set_value(value)
        self.ups_name = ups_name
        service = self.add_preload_service("BatteryService")
        self.battery_level = service.get_characteristic("BatteryLevel")
        self.charging_state = service.get_characteristic("ChargingState")
        self.status_low_battery = service.get_characteristic("StatusLowBattery")

    def extra_log_data(self, **kwargs):
        """Extra data for logging events."""
        return {"tags": {"identifier": self.ups_name, "type": "ups", **kwargs}}

    @Accessory.run_at_interval(60)
    def run(self):
        """Regularly fetch data."""
        try:
            client = PyNUTClient()
            data = client.list_vars(self.ups_name)
        except Exception as e:
            logger.exception(e, extra=self.extra_log_data())
            data = {
                "battery.charge": "100",
                "battery.charge.low": "20",
                "ups.status": "OL",
            }

        battery_level = int(data["battery.charge"])
        battery_threshold = int(data["battery.charge.low"])
        is_low = 1 if battery_level <= battery_threshold else 0

        self.battery_level.set_value(battery_level)
        self.status_low_battery.set_value(is_low)
        self.charging_state.set_value(1 if data["ups.status"] == "OL" else 0)


class UPSMonitoringPlugin(HomekitPlugin):
    """Plugin for local UPS services, on Linux hosts."""

    config_prefix = "ups"

    def __init__(self, config):
        """init function."""
        super().__init__(config)
        self.ups_names: List[str] = []
        self.sensors: List[UPSSensor] = []

    def load_config(self, parser: ConfigParser, section):
        """Load a configuration section."""
        logger.debug(f"loading {section}")
        config_errors = []
        ups_name = parser.get(section, "name", fallback=None)
        if ups_name is None:
            msg = f"Invalid option name in section {section}."
            config_errors.append(msg)
            logger.fatal(msg)
        self.ups_names.append(ups_name)
        logger.info(
            f"Configuration for monitoring {ups_name} added.",
            extra={"tags": {"type": "internet"}},
        )
        return config_errors

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        try:
            client = PyNUTClient()
        except PyNUTError as e:
            logger.exception(e)
            return
        available_upses = client.list_ups()

        for ups_name in self.ups_names:
            ups_verbose_name = available_upses.get(ups_name)
            try:
                ups_data = client.list_vars(ups_name)
                sensor = UPSSensor(bridge.driver, ups_name, ups_verbose_name, ups_data)
                self.sensors.append(sensor)
                bridge.add_accessory(sensor)
            except PyNUTError as e:
                logger.exception(e)
