# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file __main__.py is part of DiagralHomekit.                            #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""main module."""
import argparse
import logging
import os
import pathlib
import signal
import urllib.parse
from multiprocessing.pool import ThreadPool

import logging_loki
import sentry_sdk

# noinspection PyPackageRequirements
from pyhap.accessory import Bridge

# noinspection PyPackageRequirements
from pyhap.accessory_driver import AccessoryDriver

from diagralhomekit.homekit_config import HomekitDiagralConfig
from diagralhomekit.utils import capture_some_exception

logger = logging.getLogger("diagralhomekit")


def main():
    """parse arguments and run the daemons."""
    parser = argparse.ArgumentParser()
    default_port = int(os.environ.get("DIAGRAL_PORT", "51826"))
    default_config_dir = os.environ.get("DIAGRAL_CONFIG", "/etc/diagralhomekit")
    default_sentry_dsn = os.environ.get("DIAGRAL_SENTRY_DSN")
    default_loki_url = os.environ.get("DIAGRAL_LOKI_URL")
    parser.add_argument("-p", "--port", type=int, default=default_port)
    parser.add_argument(
        "-C",
        "--config-dir",
        default=pathlib.Path(default_config_dir),
        type=pathlib.Path,
    )
    parser.add_argument("--sentry-dsn", default=default_sentry_dsn)
    parser.add_argument("--loki-url", default=default_loki_url)
    args = parser.parse_args()
    config_dir = args.config_dir

    if args.sentry_dsn:
        sentry_sdk.init(args.sentry_dsn)

    if args.loki_url:
        parsed_url = urllib.parse.urlparse(args.loki_url)
        url = f"{parsed_url.scheme}://{parsed_url.hostname}"
        if parsed_url.port:
            url += f":{parsed_url.port}"
        url += parsed_url.path
        if parsed_url.query:
            url += f"?{parsed_url.query}"
        handler = logging_loki.LokiHandler(
            url=url,
            tags={"application": "diagralhomekit"},
            auth=(parsed_url.username or "", parsed_url.password or ""),
            version="1",
        )
        logger.addHandler(handler)
    listen_port = args.port

    run_daemons(config_dir, listen_port)


def run_daemons(config_dir, listen_port):
    """launch all processes: Homekit and Diagral checker."""
    persist_file = config_dir / "persist.json"
    config_file = config_dir / "config.ini"
    thread_pool = ThreadPool(1)
    driver = AccessoryDriver(port=listen_port, persist_file=persist_file)
    bridge = Bridge(driver, "Diagral e-One")
    config = HomekitDiagralConfig(bridge)
    try:
        config.load_config(config_file)
        driver.add_accessory(accessory=bridge)
        signal.signal(signal.SIGTERM, driver.signal_handler)
        thread_pool.apply_async(config.run)
        driver.start()
    except ValueError as e:
        print(e)
        raise e
    except Exception as e:
        capture_some_exception(e)
        raise e
    config.continue_loop = False


if __name__ == "__main__":
    """Allow to use "python3 -m diagralhomekit" ."""
    main()
