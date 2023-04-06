# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file homekit.py is part of DiagralHomekit.                             #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Implements a generic Homekit accessory."""
import logging

# noinspection PyPackageRequirements
from pyhap.accessory import Accessory

# noinspection PyPackageRequirements
from pyhap.accessory_driver import AccessoryDriver

# noinspection PyPackageRequirements
from pyhap.const import CATEGORY_ALARM_SYSTEM

from diagralhomekit.alarm_system import AlarmSystem
from diagralhomekit.utils import BASE_AID, capture_some_exception

logger = logging.getLogger(__name__)


class HomekitAlarm(Accessory):
    """Represent a generic Homekit alarm object."""

    STATE_STAY_ARM = 0
    STATE_AWAY_ARM = 1
    STATE_NIGHT_ARM = 2
    STATE_DISARMED = 3
    STATE_ALARM_TRIGGERED = 4
    category = CATEGORY_ALARM_SYSTEM
    state_texts = {
        STATE_STAY_ARM: "stay arm",
        STATE_AWAY_ARM: "away arm",
        STATE_NIGHT_ARM: "night arm",
        STATE_DISARMED: "disarmed",
        STATE_ALARM_TRIGGERED: "alarm triggered",
    }

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
            state = self.STATE_DISARMED
            groups = set()
        extra = self.alarm_system.extra_log_data(
            state=self.state_texts[state], action="set"
        )
        logger.info(
            f"State {self.state_texts[state]} required for {self.alarm_system.name}.",
            extra=extra,
        )
        self.alarm_target_state.set_value(state)
        self.required_target_state = state
        try:
            self.alarm_system.activate_groups(groups)
        except Exception as e:
            logger.exception(e, extra=extra)
            capture_some_exception(e)

    @Accessory.run_at_interval(10)
    def run(self):
        """Check if something has changed."""
        fault = 1 if self.alarm_system.status_fault else 0
        self.sensor_status_fault.set_value(fault)
        self.alarm_status_fault.set_value(fault)
        active_groups = self.alarm_system.get_active_groups()
        stay_groups = self.alarm_system.get_stay_groups()
        night_groups = self.alarm_system.get_night_groups()

        log_level = logging.INFO
        if self.alarm_system.is_triggered and active_groups:
            state = self.STATE_ALARM_TRIGGERED
            log_level = logging.WARNING
        elif active_groups.issuperset(stay_groups) and active_groups.issuperset(
            night_groups
        ):
            state = self.STATE_AWAY_ARM
        elif active_groups.issuperset(stay_groups):
            state = self.STATE_STAY_ARM
        elif active_groups.issuperset(night_groups):
            state = self.STATE_NIGHT_ARM
        else:
            state = self.STATE_DISARMED

        self.sensor_status_active.set_value(state != self.STATE_DISARMED)
        self.sensor_occupancy_detected.set_value(state == self.STATE_ALARM_TRIGGERED)
        self.alarm_alarm_type.set_value(1 if state == self.STATE_ALARM_TRIGGERED else 0)

        if self.alarm_current_state.get_value() != state:
            extra = self.alarm_system.extra_log_data(
                state=self.state_texts[state], action="changed"
            )
            logger.log(
                log_level,
                f"State {self.state_texts[state]} set for {self.alarm_system.name}.",
                extra=extra,
            )
        if (
            self.alarm_target_state.get_value() != state
            and state != self.STATE_ALARM_TRIGGERED
        ):
            if self.required_target_state is None:
                # indicate an external change (through the native app)
                self.alarm_target_state.set_value(state)
            elif self.required_target_state == state:
                extra = self.alarm_system.extra_log_data(
                    state=self.state_texts[state], action="reached"
                )
                logger.info(
                    f"State {self.state_texts[state]} reached by {self.alarm_system.name}.",
                    extra=extra,
                )
                self.required_target_state = None

        self.alarm_current_state.set_value(state)
