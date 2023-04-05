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
import pathlib
import re
import time
from threading import Lock
from typing import Dict, Optional, Set, Tuple

import requests
from sentry_sdk import capture_exception

from diagralhomekit.alarm_system import AlarmSystem
from diagralhomekit.utils import (
    RegexValidator,
    bool_validator,
    capture_some_exception,
    sleep,
)


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
        return {1}

    def get_night_groups(self) -> Set[int]:
        """return the selected groups for night configuration."""
        return {2}

    def create_new_session(self, count=0):
        """Create a new session."""
        if count >= self.account.config.max_request_tries:
            raise ValueError("Unable to get alarm status")
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
            raise ValueError("masterCode invalid. Please verify your configuration.")
        elif message == "transmitter.connection.sessionalreadyopen":
            last_ttm_session_id = self.get_last_ttm_session_id()
            self.disconnect_session(last_ttm_session_id)
            return self.create_new_session(count=count + 1)
        raise ValueError("ttmSessionId is not in the response. Please retry later.")

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
            raise ValueError("Unable to get alarm status")
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
            sleep()
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
            raise ValueError("Unable to get alarm status")
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
            sleep()
            return self.send_activation_command(groups=groups, count=count + 1)
        content = r.json()
        if content["commandStatus"] != "CMD_OK":
            raise ValueError("Error during activation.")
        self.set_active_groups(set(content["groups"]))

    def deactivate_alarm(self, count=0):
        """Deactivate the alarm."""
        if count >= self.account.config.max_request_tries:
            raise ValueError("Unable to request alarm deactivation")
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
            sleep()
            return self.deactivate_alarm(count=count + 1)
        content = r.json()
        if content["commandStatus"] != "CMD_OK":
            raise ValueError("Complete deactivation completed")


class DiagralAccount:
    """Represent a Diagral account."""

    def __init__(self, config, login: str, password: str):
        """init function."""
        self.config = config
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

    def __str__(self):
        """Return a string."""
        return f"DiagralAccount('{self.login})"

    def get_alarm_system(self, system_id: int, **kwargs) -> AlarmSystem:
        """Get an alarm system identified by its id."""
        if system_id not in self.alarm_systems:
            self.alarm_systems[system_id] = DiagralAlarmSystem(
                self, system_id, **kwargs
            )
        return self.alarm_systems[system_id]

    def request(self, endpoint, json_data=None, data=None, method="POST"):
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
            params=data,
            json=json_data,
            headers=headers,
            timeout=60,
        )
        # print(f"=== {url} {r.status_code}===")
        # if r.status_code != 500:
        #     print(r.text)
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
                system.role = system_data["role"]
                system.internal_name = system_data["name"]
                system.installation_complete = system_data["installationComplete"]
                system.standalone = system_data["standalone"]

    def check_alarm_emails(self):
        """Check for new emails."""
        max_document_size = 100000
        if not self.imap_login or not self.imap_hostname:
            return
        cls = imaplib.IMAP4
        if self.imap_use_tls:
            cls = imaplib.IMAP4_SSL

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
            typ, data = imap_client.search(None, "NOT DELETED")
            if typ != "OK":
                raise ValueError("Unable to perform an IMAP search for new messages.")
            # noinspection PyUnresolvedReferences
            for message_num in data[0].decode().split():
                typ, data = imap_client.fetch(message_num, "(RFC822.SIZE)")
                # noinspection PyUnresolvedReferences
                id_size = data[0].decode()
                matcher = re.match(r".+ \(RFC822.SIZE (\d+)\)$", id_size)
                if not matcher or typ != "OK":
                    print(f"Unable to fetch the size of message {message_num}")
                    continue
                message_size = int(matcher.group(1))
                if message_size <= max_document_size:
                    typ, data = imap_client.fetch(message_num, "(RFC822)")
                    if typ != "OK":
                        # noinspection PyUnresolvedReferences
                        print(
                            "unable to fetch message %s (%s)"
                            % (
                                message_num,
                                data[0].decode()
                                if data and data[0]
                                else "unknown error",
                            )
                        )
                        continue
                    # noinspection PyUnresolvedReferences
                    message_text = data[0][1].decode()
                    self.analyze_single_email(message_text)
                imap_client.store(message_num, "+FLAGS", r"(\Deleted)")
            imap_client.expunge()

    def analyze_single_email(self, content: str):
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
        for system in self.alarm_systems.values():
            if line.endswith(system.internal_name + " : Alarme"):
                system.is_triggered = True
                system.trigger_date = datetime.datetime.now(tz=datetime.UTC)

    def update_all_systems(self):
        """Update all system with a few requests."""
        with self.request_lock:
            self.do_login()
            for system in self.alarm_systems.values():
                system.create_new_session()
                system.disconnect_session()
            self.do_logout()
            time.sleep(1)

    def change_alarm_state(self, system: DiagralAlarmSystem, groups: Set[int]):
        """Change the alarm state."""
        with self.request_lock:
            self.do_login()
            system.create_new_session()
            system.send_activation_command(groups)
            system.disconnect_session()
            self.do_logout()
            time.sleep(1)


class DiagralConfig:
    """Diagral configuration, with multiple accounts."""

    max_request_tries = 3
    _account_requirements = {
        "login": RegexValidator(r".*@.*\..*"),
        "password": str,
        "system_id": int,
        "transmitter_id": RegexValidator(r"[\dA-F]*"),
        "central_id": RegexValidator(r"[\dA-F]*"),
        "master_code": int,
        "name": str,
    }
    _imap_requirements = {
        "imap_login": str,
        "imap_password": str,
        "imap_hostname": str,
        "imap_port": int,
        "imap_use_tls": bool_validator,
    }

    def __init__(self):
        """init function."""
        self.accounts: [Tuple[str, str], DiagralAccount] = {}
        self.continue_loop = True
        self.update_interval_in_s = 30
        self.diagral_multiplier = 5

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
            for kwarg, checker in self._account_requirements.items():
                raw_value = parser.get(section, kwarg, fallback=None)
                if raw_value is None:
                    config_errors.append(
                        f"Required option {kwarg} in section {section}."
                    )
                    continue
                elif raw_value is not None:
                    try:
                        kwargs[kwarg] = checker(raw_value)
                    except ValueError:
                        config_errors.append(
                            f"Invalid option {kwarg} in section {section}."
                        )
                        continue
            login, password = kwargs.pop("login"), kwargs.pop("password")
            account = self.get_account(login, password)

            # allow to connect to IMAP accounts for fetching alarm emails
            for attr, checker in self._imap_requirements.items():
                raw_value = parser.get(section, attr, fallback=None)
                if raw_value is not None:
                    setattr(account, attr, checker(raw_value))

            account.get_alarm_system(**kwargs)
        if config_errors:
            raise ValueError("\n".join(config_errors))

    def run(self):
        """Run all daemons."""
        for account in self.accounts.values():
            account.do_login()
            account.initialize_systems()
            account.do_logout()
        while self.continue_loop:
            for account in self.accounts.values():
                try:
                    account.update_all_systems()
                except Exception as e:
                    capture_some_exception(e)
            for __ in range(self.diagral_multiplier):
                for account in self.accounts.values():
                    try:
                        account.check_alarm_emails()
                    except Exception as e:
                        capture_some_exception(e)
                time.sleep(self.update_interval_in_s)
