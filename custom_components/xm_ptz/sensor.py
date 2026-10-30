"""Diagnostic sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import XMConfigEntry, XMCoordinator
from .entity import XMEntity


async def async_setup_entry(hass: HomeAssistant, entry: XMConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([XMClockOffset(entry.runtime_data.coordinator)])


class XMClockOffset(XMEntity, SensorEntity):
    """Seconds the camera clock is ahead of Home Assistant (after any automatic correction)."""

    _attr_name = "Clock offset"
    _attr_icon = "mdi:clock-alert-outline"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: XMCoordinator) -> None:
        super().__init__(coordinator, "clock_offset")

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("clock_offset")
