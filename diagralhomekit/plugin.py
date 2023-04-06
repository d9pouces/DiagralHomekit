# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file plugin.py is part of DiagralHomekit.                              #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Base plugin class."""


class HomekitPlugin:
    """Generic plugin that represent a Homekit accessory."""

    config_prefix: str = ""

    def __init__(self, config):
        """init function."""
        self.config = config

    def load_config(self, parser, section):
        """Load a configuration section."""
        raise NotImplementedError

    def run_all(self):
        """Run all daemons in separate threads."""
        pass

    def stop_all(self):
        """Stop all accounts."""
        pass

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        raise NotImplementedError
