# noinspection PyPackageRequirements
from pyhap.accessory import Accessory
# noinspection PyPackageRequirements
from pyhap.accessory_driver import AccessoryDriver
# noinspection PyPackageRequirements
from pyhap.const import CATEGORY_ALARM_SYSTEM

from diagralhomekit.config import DiagralAlarmSystem
from diagralhomekit.utils import BASE_AID


class HomekitAlarm(Accessory):
    STATE_STAY_ARM = 0
    STATE_AWAY_ARM = 1
    STATE_NIGHT_ARM = 2
    STATE_DISARMED = 3
    STATE_ALARM_TRIGGERED = 4
    category = CATEGORY_ALARM_SYSTEM

    def __init__(self, system: DiagralAlarmSystem,
                 driver: AccessoryDriver):
        super().__init__(driver, system.name, aid=system.system_id + BASE_AID)

        self.info_service = self.get_service("AccessoryInformation")
        self.info_service.get_characteristic("Identify").set_value(True)
        self.info_service.get_characteristic("Manufacturer").set_value("Diagral")
        self.info_service.get_characteristic("Model").set_value("e-One")
        self.info_service.get_characteristic("Name").set_value(system.name)
        self.info_service.get_characteristic("SerialNumber").set_value(str(system.central_id))

        self.security_service = self.add_preload_service(
            "SecuritySystem", chars=["StatusFault", "AlarmType"]
        )
        self.security_status_fault = self.security_service.get_characteristic("StatusFault")
        self.security_alarm_type = self.security_service.get_characteristic("AlarmType")
        self.security_current_state = self.security_service.configure_char(
            "SecuritySystemCurrentState",
            value=self.STATE_DISARMED,
        )
        self.security_target_state = self.security_service.configure_char(
            "SecuritySystemTargetState",
            setter_callback=self.set_target_state,
            value=self.STATE_DISARMED,
        )

        self.sensor_service = self.add_preload_service("OccupancySensor", chars=["StatusFault"])
        self.sensor_service.occupancy_detected = self.sensor_service.get_characteristic("OccupancyDetected")
        self.sensor_service.occupancy_status_fault = self.sensor_service.get_characteristic("StatusFault")
        self.sensor_service.occupancy_status_active = self.sensor_service.get_characteristic("StatusActive")
        self.run()

    def set_target_state(self, value: int):
        pass
