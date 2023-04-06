# ##############################################################################
#  Copyright (c) Matthieu Gallet <github@19pouces.net> 2023.                   #
#  This file test_config.py is part of DiagralHomekit.                         #
#  Please check the LICENSE file for sharing or distribution permissions.      #
# ##############################################################################
"""Basic unittests."""
from unittest.mock import patch

from diagralhomekit.diagral_config import (
    DiagralAccount,
    DiagralAlarmSystem,
    HomekitConfig,
)
from diagralhomekit_tests.constants import request_mock


@patch("diagralhomekit.diagral_config.DiagralAccount.request", new=request_mock)
def test_login():
    """Test the login."""
    config = HomekitConfig()
    account = DiagralAccount(config, "diagral@example.com", "wrong")
    assert not account.do_login()
    account = DiagralAccount(config, "diagral@example.com", "p4ssw0rD")
    assert account.do_login()
    account.do_logout()


@patch("diagralhomekit.diagral_config.DiagralAccount.request", new=request_mock)
def test_initialize_systems():
    """Test the initialize_systems function."""
    config = HomekitConfig()
    account = DiagralAccount(config, "diagral@example.com", "p4ssw0rD")
    assert account.do_login()
    systems = account.initialize_systems()
    assert len(systems) == 3
    account.do_logout()


@patch("diagralhomekit.diagral_config.DiagralAccount.request", new=request_mock)
def test_get_central_status():
    """Test the get_central_status function."""
    config = HomekitConfig()
    account = DiagralAccount(config, "diagral@example.com", "p4ssw0rD")
    account.is_running = False
    assert account.do_login()
    system = account.get_alarm_system(
        81838,
        transmitter_id="123456789ABCDE",
        central_id="123456789ABCF0",
        master_code=8888,
        name="Home",
    )
    data = system.get_central_status()
    system.analyze_central_status(data)
    assert system.status_fault
    account.do_logout()
