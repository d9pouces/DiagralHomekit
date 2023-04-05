# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file homekit.py is part of DiagralHomekit.                             #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Implements a generic Homekit accessory."""
# noinspection PyPackageRequirements
from pyhap.accessory import Accessory

# noinspection PyPackageRequirements
from pyhap.accessory_driver import AccessoryDriver

# noinspection PyPackageRequirements
from pyhap.const import CATEGORY_ALARM_SYSTEM

from diagralhomekit.alarm_system import AlarmSystem
from diagralhomekit.utils import BASE_AID, capture_some_exception


class HomekitAlarm(Accessory):
    """Represent a generic Homekit alarm object."""

    STATE_STAY_ARM = 0
    STATE_AWAY_ARM = 1
    STATE_NIGHT_ARM = 2
    STATE_DISARMED = 3
    STATE_ALARM_TRIGGERED = 4
    category = CATEGORY_ALARM_SYSTEM

    def __init__(self, system: AlarmSystem, driver: AccessoryDriver):
        """init function."""
        super().__init__(driver, system.name, aid=system.identifier + BASE_AID)

        self.info_service = self.get_service("AccessoryInformation")
        self.info_service.get_characteristic("Identify").set_value(True)
        self.info_service.get_characteristic("Manufacturer").set_value("Diagral")
        self.info_service.get_characteristic("Model").set_value("e-One")
        self.info_service.get_characteristic("Name").set_value(system.name)
        self.info_service.get_characteristic("SerialNumber").set_value(
            str(system.serial_number)
        )

        self.alarm = self.add_preload_service(
            "SecuritySystem", chars=["StatusFault", "SecuritySystemAlarmType"]
        )
        self.alarm_status_fault = self.alarm.get_characteristic("StatusFault")
        self.alarm_alarm_type = self.alarm.get_characteristic("SecuritySystemAlarmType")
        self.alarm_current_state = self.alarm.configure_char(
            "SecuritySystemCurrentState",
            value=self.STATE_DISARMED,
        )
        self.alarm_target_state = self.alarm.configure_char(
            "SecuritySystemTargetState",
            setter_callback=self.set_target_state,
            value=self.STATE_DISARMED,
        )

        self.sensor = self.add_preload_service(
            "OccupancySensor", chars=["StatusFault", "StatusActive"]
        )
        self.sensor_occupancy_detected = self.sensor.get_characteristic(
            "OccupancyDetected"
        )
        self.sensor_status_fault = self.sensor.get_characteristic("StatusFault")
        self.sensor_status_active = self.sensor.get_characteristic("StatusActive")

        self.alarm_system = system
        self.required_target_state = None

    def set_target_state(self, state: int):
        """Receive a command from the user."""
        if state == self.STATE_STAY_ARM:
            groups = self.alarm_system.get_stay_groups()
        elif state == self.STATE_NIGHT_ARM:
            groups = self.alarm_system.get_night_groups()
        elif state == self.STATE_AWAY_ARM:
            groups = (
                self.alarm_system.get_stay_groups()
                | self.alarm_system.get_night_groups()
            )
        else:
            groups = set()
        self.alarm_target_state.set_value(state)
        self.required_target_state = state
        try:
            self.alarm_system.activate_groups(groups)
        except Exception as e:
            capture_some_exception(e)

    @Accessory.run_at_interval(30)
    def run(self):
        """Check if something has changed."""
        fault = 1 if self.alarm_system.status_fault else 0
        self.sensor_status_fault.set_value(fault)
        self.alarm_status_fault.set_value(fault)
        active_groups = self.alarm_system.get_active_groups()

        if self.alarm_system.is_triggered and active_groups:
            self.alarm_current_state.set_value(self.STATE_ALARM_TRIGGERED)
            self.sensor_occupancy_detected.set_value(True)
            self.sensor_status_active.set_value(True)
            self.alarm_alarm_type.set_value(1)
            return

        self.sensor_occupancy_detected.set_value(False)
        self.alarm_alarm_type.set_value(0)
        stay_groups = self.alarm_system.get_stay_groups()
        night_groups = self.alarm_system.get_night_groups()
        if active_groups.issuperset(stay_groups) and active_groups.issuperset(
            night_groups
        ):
            state = self.STATE_AWAY_ARM
            self.sensor_status_active.set_value(True)
        elif active_groups.issuperset(stay_groups):
            state = self.STATE_STAY_ARM
            self.sensor_status_active.set_value(True)
        elif active_groups.issuperset(night_groups):
            state = self.STATE_NIGHT_ARM
            self.sensor_status_active.set_value(True)
        else:
            state = self.STATE_DISARMED
            self.sensor_status_active.set_value(False)
        self.alarm_current_state.set_value(state)
        if self.required_target_state is None:
            self.alarm_target_state.set_value(state)
        elif self.required_target_state == state:
            self.required_target_state = None
