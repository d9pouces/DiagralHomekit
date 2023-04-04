import argparse
import pathlib
import sentry_sdk
import signal
# noinspection PyPackageRequirements
from pyhap.accessory import Bridge
# noinspection PyPackageRequirements
from pyhap.accessory_driver import AccessoryDriver

from diagralhomekit.homekit_config import HomekitDiagralConfig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=51826)
    parser.add_argument("-C", "--config-dir", default=pathlib.Path("/etc/diagralhomekit"), type=pathlib.Path)
    parser.add_argument("--sentry-dsn", default=None)

    args = parser.parse_args()
    config_dir = args.config_dir
    persist_file = config_dir / "persist.json"
    config_file = config_dir / "config.ini"
    if args.sentry_dsn:
        sentry_sdk.init(args.sentry_dsn)
    driver = AccessoryDriver(port=args.port, persist_file=persist_file)
    bridge = Bridge(driver, "Diagral e-One")
    config = HomekitDiagralConfig(bridge)
    try:
        config.load_config(config_file)
        driver.add_accessory(accessory=bridge)
        signal.signal(signal.SIGTERM, driver.signal_handler)
        driver.start()
    except ValueError as e:
        print(e)


if __name__ == "__main__":
    """Allow to use "python3 -m hkc" instead of "hkc-ctl"."""
    main()
