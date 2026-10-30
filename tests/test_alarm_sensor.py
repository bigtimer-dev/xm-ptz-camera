"""Offline test of the alarm sensor hold logic."""
from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.xm_ptz.binary_sensor import SENSORS, XMAlarmSensor


async def test_person_hold(hass):
    coordinator = MagicMock(serial="SN", info={}, api=MagicMock(host="h"))
    sensor = XMAlarmSensor(coordinator, next(d for d in SENSORS if d.key == "person"))
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.test_person"
    sensor.async_write_ha_state = MagicMock()
    event = "appEventHumanDetectAlarm"
    sensor._on_alarm({"Event": event, "Status": "Start"})
    assert sensor.is_on
    sensor._on_alarm({"Event": event, "Status": "Stop"})
    assert sensor.is_on  # held after Stop
    sensor._on_alarm({"Event": "VideoBlind", "Status": "Start"})  # other sensor's event is ignored
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert not sensor.is_on
