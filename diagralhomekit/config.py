# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file config.py is part of DiagralHomekit.                              #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Global configuration for Homekit devices."""
import configparser
import pathlib
import re

import systemlogger

from diagralhomekit.http_plugin import HttpMonitoringPlugin
from diagralhomekit.meteofrance import MeteoFrancePlugin
from diagralhomekit.nut import UPSMonitoringPlugin
from diagralhomekit.plex import PlexHomekitPlugin

logger = systemlogger.getLogger(__name__)


class HomekitConfig:
    """Diagral configuration, with multiple accounts."""

    max_request_tries = 3

    def __init__(self):
        """init function."""
        from diagralhomekit.diagral import DiagralHomekitPlugin

        self.verbosity = False
        self.plugins = [
            DiagralHomekitPlugin(self),
            PlexHomekitPlugin(self),
            HttpMonitoringPlugin(self),
            MeteoFrancePlugin(self),
            UPSMonitoringPlugin(self),
        ]

    def load_config(self, config_file: pathlib.Path):
        """Load the configuration."""
        parser = configparser.ConfigParser()
        parser.read(config_file)
        config_errors = []
        for section in parser.sections():
            matcher = re.match(r"(.*):(.*)", section)
            if not matcher:
                continue
            prefix = matcher.group(1)
            for plugin in self.plugins:
                if plugin.config_prefix == prefix:
                    config_errors += plugin.load_config(parser, section)
                    break
            else:
                config_errors.append(f"Unknown plugin {prefix} in section {section}")
        if config_errors:
            raise ValueError("\n".join(config_errors))

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        for plugin in self.plugins:
            plugin.load_accessories(bridge)

    def run_all(self):
        """Run all daemons in separate threads."""
        for plugin in self.plugins:
            plugin.run_all()

    def stop_all(self):
        """Stop all accounts."""
        for plugin in self.plugins:
            plugin.stop_all()
