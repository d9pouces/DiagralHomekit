# noinspection PyPackageRequirements
from pyhap.accessory import Bridge
from typing import Dict

from diagralhomekit.diagral_config import DiagralAccount, DiagralAlarmSystem, DiagralConfig
from diagralhomekit.homekit import HomekitAlarm


class HomekitDiagralConfig(DiagralConfig):
    def __init__(self, bridge: Bridge):
        super().__init__()
        self.bridge = bridge


class HomekitDiagralAccount(DiagralAccount):

    def __init__(self, config: HomekitDiagralConfig, login: str, password: str):
        super().__init__(config, login, password)
        self.accessories: Dict[int, HomekitAlarm] = {}

    def get_alarm_system(self, system_id: int, **kwargs) -> DiagralAlarmSystem:
        alarm_system = super().get_alarm_system(system_id, **kwargs)
        if system_id not in self.accessories:
            self.accessories[system_id] = HomekitAlarm(alarm_system, self.config.bridge.driver)
            self.config.bridge.add_accessory(self.accessories[system_id])
        return self.alarm_systems[system_id]
