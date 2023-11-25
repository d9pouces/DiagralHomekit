# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file meteofrance.py is part of DiagralHomekit.                         #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Add weather sensor that takes data from the MeteoFrance website."""
import time
from configparser import ConfigParser
from multiprocessing.pool import ThreadPool
from typing import Dict, List

import systemlogger
from meteofrance_api import MeteoFranceClient
from meteofrance_api.model import Place

# noinspection PyPackageRequirements
from pyhap.accessory import Accessory

# noinspection PyPackageRequirements
from pyhap.const import CATEGORY_SENSOR

from diagralhomekit.plugin import HomekitPlugin

logger = systemlogger.getLogger(__name__)


class MeteoFranceSensor(Accessory):
    """Weather sensor using MétéoFrance data."""

    info_by_service = {
        "temperature_max": (
            "Température max",
            "TemperatureSensor",
            "CurrentTemperature",
        ),
        "temperature_min": (
            "Température min",
            "TemperatureSensor",
            "CurrentTemperature",
        ),
        "humidity_min": ("Humidité max", "HumiditySensor", "CurrentRelativeHumidity"),
        "humidity_max": ("Humidité min", "HumiditySensor", "CurrentRelativeHumidity"),
        "rain_forecast": ("Pluie dans l'heure", "OccupancySensor", "OccupancyDetected"),
    }
    category = CATEGORY_SENSOR

    def __init__(self, driver, place: Place, char_name):
        """init function."""
        service_info = self.info_by_service[char_name]
        aid = hash(place.name + char_name)
        name = f"{service_info[0]} à {place.name}"
        super().__init__(driver, name, aid=aid)
        self.place = place

        info_service = self.get_service("AccessoryInformation")
        info_service.get_characteristic("Identify").set_value(False)
        info_service.get_characteristic("Manufacturer").set_value("MétéoFrance")
        info_service.get_characteristic("Model").set_value(service_info[0])
        info_service.get_characteristic("Name").set_value(name)

        service = self.add_preload_service(service_info[1], chars=["StatusFault"])
        self.service_char = service.configure_char(service_info[2])
        self.status_fault = service.configure_char("StatusFault")


class MeteoFranceLocation:
    """Represent a location to check."""

    def __init__(self, config, place: Place):
        """init function."""
        self.config = config
        self.place = place
        self.sensors: Dict[str, MeteoFranceSensor] = {}
        self.is_running = True

    def __str__(self):
        """Return a string."""
        return f"Place('{self.place.name})"

    def extra_log_data(self, **kwargs):
        """Extra data for logging events."""
        return {
            "tags": {"identifier": self.place.name, "type": "meteofrance", **kwargs}
        }

    def sleep_while_run(self, interval_in_s: int):
        """Sleep for the given interval if active."""
        for __ in range(interval_in_s * 10):
            if not self.is_running:
                return
            time.sleep(0.1)

    def run(self):
        """Continuously update the systems and looks for weather changes."""
        extra = self.extra_log_data()
        while self.is_running:
            logger.debug(f"Update weather data for {self.place.name}", extra=extra)
            try:
                self.update_all_sensors()
            except Exception as e:
                logger.exception(e)
                for sensor in self.sensors.values():
                    sensor.status_fault.set_value(1)
            self.sleep_while_run(300)

    def update_all_sensors(self):
        """Update all weather sensors."""
        client = MeteoFranceClient()
        my_place_weather_forecast = client.get_forecast_for_place(self.place)
        data = my_place_weather_forecast.daily_forecast[0]
        for char_name, sensor in self.sensors.items():
            if char_name == "temperature_max":
                sensor.service_char.set_value(data["T"]["max"])
            elif char_name == "temperature_min":
                sensor.service_char.set_value(data["T"]["min"])
            elif char_name == "humidity_min":
                sensor.service_char.set_value(data["humidity"]["max"])
            elif char_name == "humidity_max":
                sensor.service_char.set_value(data["humidity"]["min"])
            elif char_name == "rain_forecast":
                forecast = client.get_rain(self.place.latitude, self.place.longitude)
                if forecast.next_rain_date_locale():
                    sensor.service_char.set_value(1)
                else:
                    sensor.service_char.set_value(0)
            sensor.status_fault.set_value(0)


class MeteoFrancePlugin(HomekitPlugin):
    """Plugin for weather predictions."""

    config_prefix = "meteofrance"
    requirements = {
        "name": str,
        "latitude": float,
        "longitude": float,
        "country": str,
        "region": str,
    }

    def __init__(self, config):
        """init function."""
        super().__init__(config)
        self.locations: List[MeteoFranceLocation] = []
        self.thread_pool = None

    def load_config(self, parser: ConfigParser, section):
        """Load a configuration section."""
        logger.debug(f"loading {section}")
        config_errors = []
        kwargs = {}
        for kwarg, checker in self.requirements.items():
            raw_value = parser.get(section, kwarg, fallback=None)
            if raw_value is not None:
                try:
                    kwargs[kwarg] = checker(raw_value)
                except ValueError:
                    msg = f"Invalid option {kwarg} in section {section}."
                    logger.fatal(msg)
                    config_errors.append(msg)
                    continue
        if not config_errors:
            place = Place(
                {
                    "name": kwargs["name"],
                    "lat": kwargs["latitude"],
                    "lon": kwargs["longitude"],
                    "country": kwargs["country"],
                    "admin": kwargs["region"],
                }
            )
            location = MeteoFranceLocation(self, place)
            logger.info(
                f"Configuration for weather sensor {place.name} added.",
                extra=location.extra_log_data(),
            )
            self.locations.append(location)
        return config_errors

    def run_all(self):
        """Run all daemons in separate threads."""
        if self.locations:
            self.thread_pool = ThreadPool(len(self.locations))
            for location in self.locations:
                self.thread_pool.apply_async(location.run)

    def stop_all(self):
        """Stop all accounts."""
        for location in self.locations:
            location.is_running = False

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        for location in self.locations:
            for char_name in MeteoFranceSensor.info_by_service:
                sensor = MeteoFranceSensor(bridge.driver, location.place, char_name)
                location.sensors[char_name] = sensor
                bridge.add_accessory(sensor)
