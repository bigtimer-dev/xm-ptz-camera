"""Alarm sensors fed by the camera's DVRIP alarm push (AlarmInfo: Event + Status Start/Stop)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import ALARM_AUTO_OFF, ALARM_HOLD, SIGNAL_ALARM
from .coordinator import XMConfigEntry, XMCoordinator
from .entity import XMEntity


@dataclass(frozen=True, kw_only=True)
class AlarmSensorDescription(BinarySensorEntityDescription):
    matches: Callable[[str], bool]


def _is_person(event: str) -> bool:
    return any(word in event for word in ("Human", "Ped", "Person"))


SENSORS = [
    AlarmSensorDescription(key="motion", name="Motion", device_class=BinarySensorDeviceClass.MOTION,
                           matches=lambda e: e == "VideoMotion" or ("Motion" in e and not _is_person(e))),
    AlarmSensorDescription(key="person", name="Person", device_class=BinarySensorDeviceClass.OCCUPANCY,
                           icon="mdi:human", matches=_is_person),
    AlarmSensorDescription(key="tamper", name="Camera blocked", device_class=BinarySensorDeviceClass.TAMPER,
                           matches=lambda e: e == "VideoBlind", entity_registry_enabled_default=False),
]


async def async_setup_entry(hass: HomeAssistant, entry: XMConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(XMAlarmSensor(coordinator, d) for d in SENSORS)


class XMAlarmSensor(XMEntity, BinarySensorEntity):
    entity_description: AlarmSensorDescription

    def __init__(self, coordinator: XMCoordinator, description: AlarmSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_is_on = False
        self._cancel_off: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_ALARM.format(self.coordinator.serial), self._on_alarm))
        self.async_on_remove(self._cancel_timer)

    @callback
    def _cancel_timer(self) -> None:
        if self._cancel_off:
            self._cancel_off()
            self._cancel_off = None

    @callback
    def _on_alarm(self, alarm: dict) -> None:
        if not self.entity_description.matches(str(alarm.get("Event", ""))):
            return
        self._cancel_timer()
        started = alarm.get("Status") == "Start"
        self._cancel_off = async_call_later(self.hass, ALARM_AUTO_OFF if started else ALARM_HOLD, self._auto_off)
        if started:
            self._attr_is_on = True
            self._attr_extra_state_attributes = {"event": alarm.get("Event"), "start_time": alarm.get("StartTime")}
            self.async_write_ha_state()

    @callback
    def _auto_off(self, _now) -> None:
        self._cancel_off = None
        self._attr_is_on = False
        self.async_write_ha_state()
