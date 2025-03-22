# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file plugin.py is part of DiagralHomekit.                              #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Base plugin class."""
from typing import Optional, Tuple, Iterable


class HomekitPlugin:
    """Generic plugin that represent a Homekit accessory."""

    config_prefix: str = ""

    def __init__(self, config):
        """init function."""
        self.config = config
        self.prometheus_filename: Optional[str] = None

    def load_config(self, parser, section):
        """Load a configuration section."""
        self.prometheus_filename = parser.get(section, "prometheus_filename", fallback=None)

    def run_all(self):
        """Run all daemons in separate threads."""
        pass

    def stop_all(self):
        """Stop all accounts."""
        pass

    def load_accessories(self, bridge):
        """Add accessories to the Homekit bridge."""
        raise NotImplementedError

    @property
    def prometheus_metrics_type(self) -> dict[str, str]:
        """Return the type of Prometheus metrics.

        Valid values are: "counter", "gauge", "histogram", "summary", "untyped".
        """
        return {}

    @property
    def prometheus_metrics_help(self) -> dict[str, str]:
        """Return the help for Prometheus metrics."""
        return {}

    def prometheus_write(self, values: Iterable[tuple[str, float, dict[str, str]]]):
        """Write Prometheus metrics."""
        if not self.prometheus_filename:
            return
        with open(self.prometheus_filename, "w") as fd:
            for key, value in self.prometheus_metrics_type.items():
                fd.write(f"# TYPE {key} {value}\n")
            for key, value in self.prometheus_metrics_help.items():
                fd.write(f"# HELP {key} {value}\n")
            for value_data in values:
                labels = "{" + " ".join([f'{k}="{v}"' for k, v in value_data[2].items()]) + "}"
                fd.write(f"{value_data[0]}{labels} {value_data[1]}\n")
