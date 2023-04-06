# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file diagral_config.py is part of DiagralHomekit.                      #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""A Diagral config."""
import configparser
import datetime
import email.header
import imaplib
import io
import logging
import pathlib
import re
import time
from multiprocessing.pool import ThreadPool
from threading import Lock
from typing import Dict, Optional, Set, Tuple

import requests
from sentry_sdk import capture_exception

from diagralhomekit.alarm_system import AlarmSystem
from diagralhomekit.utils import (
    RegexValidator,
    bool_validator,
    capture_some_exception,
    slugify,
)

logger = logging.getLogger(__name__)


class DiagralAlarmSystem(AlarmSystem):
    """A Diagral alarm system."""

    def __init__(
        self,
        account,
        system_id: int,
        transmitter_id: str,
        central_id: str,
        master_code: int,
        name: str,
    ):
        """init function."""
        super().__init__(name)
        self.account: DiagralAccount = account
        self.system_id = system_id
        self.transmitter_id: str = transmitter_id
        self.central_id: str = central_id
        self.master_code: int = master_code
        self.role: int = 0
        self.installation_complete: bool = True
        self.standalone: bool = False
        self.ttm_session_id: str = ""
        self.internal_name: str = "-"

    @property
    def identifier(self) -> int:
        """return a unique identifier."""
        return self.system_id

    @property
    def serial_number(self) -> str:
        """return the serial number of this system."""
        return self.central_id

    def get_stay_groups(self) -> Set[int]:
        """return the selected groups for stay configuration."""
        return {2}

    def get_night_groups(self) -> Set[int]:
        """return the selected groups for night configuration."""
        return {1}

    def create_new_session(self, count=0):
        """Create a new session."""
        if count >= self.account.config.max_request_tries:
            raise ValueError("Unable to get alarm status; please try again later.")
        r = self.account.request(
            "/authenticate/connect",
            json_data={
                "masterCode": "%04d" % self.master_code,
                "transmitterId": self.transmitter_id,
                "systemId": self.system_id,
                "role": self.role,
            },
        )
        try:
            content = r.json()
        except Exception as e:
            capture_exception(e)
            raise ValueError("Unable to connect to the system.")
        if "ttmSessionId" in content:
            self.ttm_session_id = content["ttmSessionId"]
            self.set_active_groups(set(content["groups"]))
            return self.ttm_session_id
        message = content["message"]
        if message == "transmitter.connection.badpincode":
            raise ValueError("MasterCode invalid; please verify your configuration.")
        elif message == "transmitter.connection.overlimit":
            self.account.sleep_while_run(180)
            return self.create_new_session(count=count + 1)
        elif message == "transmitter.connection.sessionalreadyopen":
            last_ttm_session_id = self.get_last_ttm_session_id()
            self.disconnect_session(last_ttm_session_id)
            return self.create_new_session(count=count + 1)
        raise ValueError("Unable to create session; please verify your configuration.")

    def get_central_status(self, count=0):
        """Return the status for all systems."""
        if count >= self.account.config.max_request_tries:
            raise ValueError("Unable to get alarm status.")
        if not self.ttm_session_id:
            self.create_new_session()
        r = self.account.request(
            "/configuration/getCentralStatusZone",
            json_data={
                "centralId": self.central_id,
                "transmitterId": self.transmitter_id,
                "systemId": self.system_id,
                "ttmSessionId": self.ttm_session_id,
            },
        )
        if r.status_code != 200:
            self.account.sleep_while_run(10)
            return self.get_central_status(count + 1)
        return r.json()

    def analyze_central_status(self, data):
        """Analyze the result provided by get_central_status(), looking for faults."""
        had_fault = self.status_fault
        self.status_fault = False
        for category, v in data.items():
            if not category.endswith("Status"):
                continue
            if isinstance(v, dict):
                v = [v]
            for sub_data in v:
                for alert_type, state in sub_data.items():
                    if alert_type.endswith("Alert") and state and not had_fault:
                        self.status_fault = True
                        extra = self.extra_log_data(action="fault")
                        msg = f"Set new {alert_type} in {category} for {self.name}."
                        logger.warning(
                            msg,
                            extra=extra,
                        )
        if had_fault and not self.status_fault:
            msg = f"Fault status cleared for {self.name}."
            logger.warning(msg, extra=self.extra_log_data(action="fault"))

    def disconnect_session(self, session: Optional[str] = None):
        """Disconnect the current session."""
        if session is None:
            session = self.ttm_session_id
        if session is None:
            return
        r = self.account.request(
            "/authenticate/disconnect",
            json_data={
                "systemId": str(self.system_id),
                "ttmSessionId": session,
            },
        )
        if r.status_code != 200:
            raise ValueError("Unable to disconnect Diagral session.")
        content = r.json()
        if content["status"] != "OK":
            raise ValueError("Disconnect Failed: %r" % content)
        self.ttm_session_id = None

    def get_last_ttm_session_id(self) -> Optional[str]:
        """Get the last TTM session id."""
        r = self.account.request(
            "/authenticate/getLastTtmSessionId", json_data={"systemId": self.system_id}
        )
        if r.status_code == 200 and r.content:
            return r.text
        return None

    def update_status(self, count=0):
        """Update the internal status."""
        if count >= self.account.config.max_request_tries:
            raise ValueError("Unable to get alarm status.")
        if not self.ttm_session_id:
            self.create_new_session()
            return
        r = self.account.request(
            "/status/getSystemState",
            json_data={
                "centralId": self.central_id,
                "ttmSessionId": self.ttm_session_id,
            },
        )
        if r.status_code != 200:
            self.account.sleep_while_run(10)
            return self.update_status(count + 1)
        content = r.json()
        self.set_active_groups(set(content["groups"]))

    def activate_groups(self, groups: Set[int]):
        """Activate some groups."""
        self.account.change_alarm_state(self, groups)

    def send_activation_command(self, groups: Set[int], count=0):
        """Activate some groups (internal function)."""
        if not groups:
            return self.deactivate_alarm()
        if count >= self.account.config.max_request_tries:
            raise ValueError("Unable to send activation command.")
        if not self.ttm_session_id:
            self.create_new_session()
        if len(groups) == 4:
            state = "on"
            groups_l = []
        else:
            state = "group"
            groups_l = list(groups)
        r = self.account.request(
            "/action/stateCommand",
            json_data={
                "systemState": state,
                "group": groups_l,
                "currentGroup": [],
                "nbGroups": "4",
                "ttmSessionId": self.ttm_session_id,
            },
        )
        if r.status_code != 200:
            self.account.sleep_while_run(10)
            return self.send_activation_command(groups=groups, count=count + 1)
        content = r.json()
        if content["commandStatus"] != "CMD_OK":
            raise ValueError("Error during activation.")
        self.set_active_groups(set(content["groups"]))

    def deactivate_alarm(self, count=0):
        """Deactivate the alarm."""
        if count >= self.account.config.max_request_tries:
            raise ValueError("Unable to request alarm deactivation.")
        if not self.ttm_session_id:
            self.create_new_session()
        r = self.account.request(
            "/action/stateCommand",
            json_data={
                "systemState": "off",
                "group": [],
                "currentGroup": [],
                "nbGroups": "4",
                "ttmSessionId": self.ttm_session_id,
            },
        )
        if r.status_code != 200:
            self.account.sleep_while_run(10)
            return self.deactivate_alarm(count=count + 1)
        content = r.json()
        if content["commandStatus"] != "CMD_OK":
            raise ValueError("Unable to complete deactivation.")


class DiagralAccount:
    """Represent a Diagral account."""

    def __init__(self, config, login: str, password: str):
        """init function."""
        self.config: DiagralConfig = config
        self.login = login
        self.password = password
        self.alarm_systems: Dict[int, DiagralAlarmSystem] = {}
        self.session_id = None
        self.diagral_id = None

        self.imap_login = ""
        self.imap_password = None
        self.imap_hostname = ""
        self.imap_port = 993
        self.imap_use_tls = True
        self.imap_directory = "INBOX"

        self.request_lock = Lock()
        self.is_running = True
        self.show_mockup_requests = False

    def __str__(self):
        """Return a string."""
        return f"DiagralAccount('{self.login})"

    def extra_log_data(self, **kwargs):
        """Extra data for logging events."""
        return {"tags": {"identifier": self.login, "type": "account", **kwargs}}

    @classmethod
    def show_basic_config(cls, login, password):
        """Display a basic configuration."""
        parser = configparser.RawConfigParser()
        config = DiagralConfig()
        account = cls(config, login, password)
        account.do_login()
        systems = account.initialize_systems()
        for system_data in systems:
            name = slugify(system_data["name"])
            section = f"system:{name}"
            parser.add_section(section)
            system_config = account.get_system_configuration(system_data["id"])
            data = {k: "" for k in config.account_requirements}
            data |= {k: "" for k in config.imap_requirements}
            data["login"] = login
            data["password"] = password
            data["name"] = system_data["name"]
            data["login"] = login
            data["system_id"] = str(system_data["id"])
            data["transmitter_id"] = system_config["transmitterId"]
            data["central_id"] = system_config["centralId"]
            parser[section] = data
        fd = io.StringIO()
        parser.write(fd)
        account.do_logout()
        return fd.getvalue()

    def get_system_configuration(self, system_id: int, count=0):
        """Return complete configuration for a given system."""
        r = self.request(
            "/configuration/getConfiguration",
            json_data={"systemId": system_id, "role": 0},
        )
        return r.json()

    def get_alarm_system(self, system_id: int, **kwargs) -> DiagralAlarmSystem:
        """Get an alarm system identified by its id."""
        if system_id not in self.alarm_systems:
            self.alarm_systems[system_id] = DiagralAlarmSystem(
                self, system_id, **kwargs
            )
        return self.alarm_systems[system_id]

    def request(self, endpoint, json_data=None, method="POST"):
        """Perform a request."""
        headers = {
            "User-Agent": "eOne/1.12.1.2 CFNetwork/1333.0.4 Darwin/21.5.0"
            "WebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "deflate",
            "X-App-Version": "1.9.1",
            "X-Identity-Provider": "JANRAIN",
            "ttmSessionIdNotRequired": "true",
            "X-Vendor": "diagral",
            "Content-Type": "application/json;charset=UTF-8",
        }
        if endpoint != "/authenticate/login":
            headers["Authorization"] = f"Bearer {self.session_id}"
            headers["X-Identity-Provider"] = "JANRAIN"
            headers["ttmSessionIdNotRequired"] = "true"
        url = f"https://appv3.tt-monitor.com/topaze{endpoint}"
        r = requests.request(
            method.lower(),
            url,
            json=json_data,
            headers=headers,
            timeout=60,
        )
        if self.config.log_requests:
            logger.debug(f"{url}: {r.status_code}")
            if r.status_code != 500:
                logger.debug(f"{r.text}")
        if self.show_mockup_requests:
            try:
                json_out = r.json()
            except requests.exceptions.JSONDecodeError:
                json_out = None
            print(
                f"""register('{endpoint}', {json_out!r}, {json_data!r}, {r.status_code})"""
            )
        return r

    def do_login(self):
        """Login to the server."""
        r = self.request(
            "/authenticate/login",
            json_data={"username": self.login, "password": self.password},
        )
        if r.status_code == 200:
            content = r.json()
            self.session_id = content["sessionId"]
            return True
        return False

    def do_logout(self):
        """Logout from the server."""
        r = self.request("/authenticate/logout", json_data={"systemId": "null"})
        if r.status_code == 401:
            return
        if r.status_code != 200:
            raise ValueError("Unable to request Logout.")
        content = r.json()
        if content["status"] != "OK":
            raise ValueError("Logout failed.")

    def initialize_systems(self):
        """Initialize all systems for getting their internal names."""
        r = self.request("/configuration/getSystems", json_data={})
        if r.status_code != 200:
            raise ValueError("Unable to request systems.")
        content = r.json()
        if "diagralId" in content:
            self.diagral_id = content["diagralId"]
        if "systems" in content:
            for system_data in content["systems"]:
                system_id = system_data["id"]
                if system_id not in self.alarm_systems:
                    continue
                system = self.alarm_systems[system_id]
                logger.debug(
                    f"Initialize system data for {system.name}",
                    extra=system.extra_log_data(),
                )
                system.role = system_data["role"]
                system.internal_name = system_data["name"]
                system.installation_complete = system_data["installationComplete"]
                system.standalone = system_data["standalone"]
        return content["systems"]

    def check_alarm_emails(self, check_count=10, check_interval_in_s=5):
        """Check for new emails."""
        if not self.imap_login or not self.imap_hostname:
            return
        logger.debug(
            f"Connect to {self.imap_login}@{self.imap_hostname}:{self.imap_port}",
            extra=self.extra_log_data(action="imap", detail="connect"),
        )
        cls = imaplib.IMAP4_SSL if self.imap_use_tls else imaplib.IMAP4

        with cls(self.imap_hostname, self.imap_port) as imap_client:
            if not self.imap_use_tls:
                try:
                    imap_client.starttls()
                except imaplib.IMAP4.error:
                    pass
            imap_client.login(self.imap_login, self.imap_password)
            typ, data = imap_client.select(mailbox=self.imap_directory, readonly=False)
            if typ != "OK":
                raise ValueError(f"Invalid mailbox {self.imap_directory}")
            to_expunge = False
            index = 0
            while index < check_count and self.is_running:
                to_expunge = self._perform_imap_search(imap_client) or to_expunge
                self.sleep_while_run(check_interval_in_s)
                index += 1
            if to_expunge:
                logger.debug(
                    f"Apply IMAP commands to {self.imap_login}@{self.imap_hostname}:{self.imap_port}",
                    extra=self.extra_log_data(action="imap", detail="apply"),
                )
                imap_client.expunge()

    def sleep_while_run(self, interval_in_s: int):
        """Sleep for the given interval if active."""
        for __ in range(interval_in_s * 10):
            if not self.is_running:
                return
            time.sleep(0.1)

    def _perform_imap_search(self, imap_client):
        """Perform an IMAP search to check for alarm emails."""
        logger.debug(
            f"Search in {self.imap_login}@{self.imap_hostname}:{self.imap_port}",
            extra=self.extra_log_data(action="imap", detail="search"),
        )
        typ, data = imap_client.search(None, "NOT DELETED")
        if typ != "OK":
            raise ValueError("Unable to perform an IMAP search for new messages.")
        max_document_size = 100000
        to_expunge = False
        # noinspection PyUnresolvedReferences
        for message_num in data[0].decode().split():
            typ, data = imap_client.fetch(message_num, "(RFC822.SIZE)")
            # noinspection PyUnresolvedReferences
            id_size = data[0].decode()
            matcher = re.match(r".+ \(RFC822.SIZE (\d+)\)$", id_size)
            if not matcher or typ != "OK":
                logger.warning(
                    f"unable to fetch the size of message {message_num}",
                    extra=self.extra_log_data(action="imap", detail="found"),
                )
                continue
            message_size = int(matcher.group(1))
            if message_size <= max_document_size:
                typ, data = imap_client.fetch(message_num, "(RFC822)")
                if typ != "OK":
                    # noinspection PyUnresolvedReferences
                    text = data[0].decode() if data and data[0] else "unknown error"
                    logger.warning(
                        f"unable to fetch message {message_num} ({text})",
                        extra=self.extra_log_data(action="imap", detail="found"),
                    )
                    continue
                # noinspection PyUnresolvedReferences
                message_text = data[0][1].decode()
                logger.debug(
                    f"Fetch email from {self.imap_login}@{self.imap_hostname}:{self.imap_port}",
                    extra=self.extra_log_data(action="imap", detail="found"),
                )
                self._analyze_single_email(message_text)
            logger.debug(
                f"Delete email {message_num} from {self.imap_login}@{self.imap_hostname}:{self.imap_port}",
                extra=self.extra_log_data(action="imap", detail="delete"),
            )
            imap_client.store(message_num, "+FLAGS", r"(\Deleted)")
            to_expunge = True
        return to_expunge

    def _analyze_single_email(self, content: str):
        """Look for emails to check if an alarm is set."""
        line = ""

        def decode(x, y):
            if isinstance(x, str):
                return x
            return x.decode(y or "utf-8")

        for line in content.splitlines():
            if not line.startswith("Subject:"):
                continue
            line = "".join(decode(x, y) for (x, y) in email.header.decode_header(line))
            break
        logger.debug(
            f"Found subject {line} in email to {self.imap_login}",
            extra=self.extra_log_data(action="imap", detail="subject"),
        )

        for system in self.alarm_systems.values():
            if line.endswith(system.internal_name + " : Alarme"):
                logger.debug(
                    f"Alarm triggered for {system.name}.",
                    extra=self.extra_log_data(action="imap", detail="alarm"),
                )
                system.is_triggered = True
                system.trigger_date = datetime.datetime.now(tz=datetime.UTC)

    def update_all_systems(self):
        """Update all system with a few requests."""
        with self.request_lock:
            self.do_login()
            for system in self.alarm_systems.values():
                try:
                    system.create_new_session()
                    status = system.get_central_status()
                    system.analyze_central_status(status)
                    system.disconnect_session()
                except Exception as e:
                    logger.exception(e, extra=system.extra_log_data())
                    capture_some_exception(e)
                    self.sleep_while_run(5)
            self.do_logout()
            self.sleep_while_run(1)

    def change_alarm_state(self, system: DiagralAlarmSystem, groups: Set[int]):
        """Change the alarm state."""
        with self.request_lock:
            self.do_login()
            system.create_new_session()
            system.send_activation_command(groups)
            system.disconnect_session()
            self.do_logout()
            time.sleep(1)

    def run(self):
        """Continuously update the systems and looks for alarms."""
        extra = self.extra_log_data()
        logger.debug(f"Initialize system data for {self.login}", extra=extra)
        self.do_login()
        self.initialize_systems()
        self.do_logout()
        while self.is_running:
            logger.debug(f"Update system data {self.login}", extra=extra)
            try:
                self.update_all_systems()
            except Exception as e:
                logger.exception(e, extra=extra)
                capture_some_exception(e)
            logger.debug(f"Check emails for system {self.login}", extra=extra)
            check_interval_in_s = 10
            try:
                self.check_alarm_emails(
                    check_count=20, check_interval_in_s=check_interval_in_s
                )
            except Exception as e:
                logger.exception(e, extra=extra)
                capture_some_exception(e)
            self.sleep_while_run(check_interval_in_s)


class DiagralConfig:
    """Diagral configuration, with multiple accounts."""

    max_request_tries = 3
    account_requirements = {
        "login": RegexValidator(r".*@.*\..*"),
        "password": str,
        "system_id": int,
        "transmitter_id": RegexValidator(r"[\dA-F]*"),
        "central_id": RegexValidator(r"[\dA-F]*"),
        "master_code": int,
        "name": str,
    }
    imap_requirements = {
        "imap_login": str,
        "imap_password": str,
        "imap_hostname": str,
        "imap_port": int,
        "imap_use_tls": bool_validator,
    }

    def __init__(self):
        """init function."""
        self.accounts: [Tuple[str, str], DiagralAccount] = {}
        self.thread_pool = None
        self.log_requests = False

    def get_account(self, login: str, password: str) -> DiagralAccount:
        """Get an account identified by the login and the password."""
        key = (login, password)
        if key not in self.accounts:
            self.accounts[key] = DiagralAccount(self, login, password)
        return self.accounts[key]

    def load_config(self, config_file: pathlib.Path):
        """Load the configuration."""
        parser = configparser.ConfigParser()
        parser.read(config_file)
        config_errors = []
        for section in parser.sections():
            if not re.match(r"system:.*", section):
                continue
            kwargs = {}
            for kwarg, checker in self.account_requirements.items():
                raw_value = parser.get(section, kwarg, fallback=None)
                if raw_value is None:
                    msg = f"Required option {kwarg} in section {section}."
                    config_errors.append(msg)
                    logger.fatal(msg)
                    continue
                elif raw_value is not None:
                    try:
                        kwargs[kwarg] = checker(raw_value)
                    except ValueError:
                        msg = f"Invalid option {kwarg} in section {section}."
                        config_errors.append(msg)
                        logger.fatal(msg)
                        continue
            login, password = kwargs.pop("login"), kwargs.pop("password")
            account = self.get_account(login, password)

            # allow to connect to IMAP accounts for fetching alarm emails
            for attr, checker in self.imap_requirements.items():
                raw_value = parser.get(section, attr, fallback=None)
                if raw_value is not None:
                    setattr(account, attr, checker(raw_value))

            system = account.get_alarm_system(**kwargs)
            logger.info(
                f"Configuration for alarm system {system} added.",
                extra=system.extra_log_data(),
            )
        if config_errors:
            raise ValueError("\n".join(config_errors))

    def run_all(self):
        """Run all daemons in separate threads."""
        self.thread_pool = ThreadPool(1)
        for account in self.accounts.values():
            self.thread_pool.apply_async(account.run)

    def stop_all(self):
        """Stop all accounts."""
        for account in self.accounts.values():
            account.is_running = False
