import configparser
import pathlib
import re
import requests
# noinspection PyPackageRequirements
from pyhap.accessory import Accessory
from sentry_sdk import capture_exception
from typing import Dict, Optional, Set, Tuple

from diagralhomekit.utils import RegexValidator, sleep


class DiagralAlarmSystem:
    def __init__(self, account, system_id: int, transmitter_id: str,
                 central_id: str, master_code: int, name: str):
        self.account = account
        self.system_id = system_id
        self.transmitter_id: str = transmitter_id
        self.central_id: str = central_id
        self.master_code: int = master_code
        self.name: str = name
        self.role: int = 0
        self.installation_complete: bool = True
        self.standalone: bool = False
        self.ttm_session_id: str = None
        self.active_groups: Set[int] = set()

    def __str__(self):
        return f"e-One('{self.name}', {self.system_id})"

    def create_new_session(self, count=0):
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
            self.active_groups = set(content["groups"])
            return
        message = content["message"]
        if message == "transmitter.connection.badpincode":
            raise ValueError("masterCode invalid. Please verify your configuration.")
        elif message == "transmitter.connection.sessionalreadyopen":
            last_ttm_session_id = self.get_last_ttm_session_id()
            self.disconnect_session(last_ttm_session_id)
            return self.create_new_session(count=count + 1)
        raise ValueError("ttmSessionId is not in the response. Please retry later.")

    def disconnect_session(self, session: Optional[str] = None):
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
            raise ValueError("Unable to disconnect session.")
        content = r.json()
        if content["status"] != "OK":
            raise ValueError("Disconnect Failed: %r" % content)
        self.ttm_session_id = None

    def get_last_ttm_session_id(self) -> Optional[str]:
        r = self.account.request(
            "/authenticate/getLastTtmSessionId", json_data={"systemId": self.system_id}
        )
        if r.status_code == 200 and r.content:
            return r.text
        return None

    def update_status(self, count=0):
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
        self.active_groups = set(content["groups"])


class DiagralAccount:
    def __init__(self, config, login: str, password: str):
        self.config = config
        self.login = login
        self.password = password
        self.alarm_systems: Dict[int, DiagralAlarmSystem] = {}
        self.session_id = None
        self.diagral_id = None

    def __str__(self):
        return f"DiagralAccount('{self.login})"

    def get_alarm_system(self, system_id: int, **kwargs) -> DiagralAlarmSystem:
        if system_id not in self.alarm_systems:
            self.alarm_systems[system_id] = DiagralAlarmSystem(self, system_id, **kwargs)
        return self.alarm_systems[system_id]

    def request(self, endpoint, json_data=None, data=None, method="POST"):
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
        print(f"=== {url} {r.status_code}===")
        if r.status_code != 500:
            print(r.text)
        return r

    def do_login(self):
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
        r = self.request("/authenticate/logout", json_data={"systemId": "null"})
        if r.status_code != 200:
            raise ValueError("Unable to request Logout.")
        content = r.json()
        if content["status"] != "OK":
            raise ValueError("Logout failed.")

    def initialize_systems(self):
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
                system.installation_complete = system_data["installationComplete"]
                system.standalone = system_data["standalone"]

    def update_systems(self):
        self.do_login()
        for instance in self.instances:
            instance.update_alarm_status()
        self.do_logout()


class DiagralConfig:
    max_request_tries = 3

    def __init__(self):
        self.accounts: [Tuple[str, str], DiagralAccount] = {}

    def get_account(self, login: str, password: str) -> DiagralAccount:
        key = (login, password)
        if key not in self.accounts:
            self.accounts[key] = DiagralAccount(self, login, password)
        return self.accounts[key]

    def load_config(self, config_file: pathlib.Path):
        parser = configparser.ConfigParser()
        parser.read(config_file)
        config_errors = []
        checkers = {
            "login": RegexValidator(r".*@.*\..*"),
            "password": str,
            "system_id": int,
            "transmitter_id": RegexValidator(r"[\dA-F]*"),
            "central_id": RegexValidator(r"[\dA-F]*"),
            "master_code": int,
            "name": str,
        }
        for section in parser.sections():
            if not re.match(r"system:.*", section):
                continue
            kwargs = {}
            for k, v in checkers.items():
                raw_value = parser.get(section, k, fallback=None)
                if raw_value is None:
                    config_errors.append(f"Required option {k} in section {section}.")
                    continue
                try:
                    kwargs[k] = v(raw_value)
                except ValueError:
                    config_errors.append(f"Invalid option {k} in section {section}.")
                    continue
                login, password = kwargs.pop("login"), kwargs.pop("password")
                account = self.get_account(login, password)
                account.get_alarm_system(**kwargs)
        if config_errors:
            raise ValueError("\n".join(config_errors))

    @Accessory.run_at_interval(305)
    def run(self):
        for account in self.accounts.values():
            account.update_systems()
