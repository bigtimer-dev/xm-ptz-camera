"""Numeric settings stored in the camera's config sections."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import Path, XMConfigEntry, XMCoordinator
from .entity import XMEntity


@dataclass(frozen=True, kw_only=True)
class ConfigNumberDescription(NumberEntityDescription):
    section: str
    path: Path


NUMBERS = [
    ConfigNumberDescription(key="motion_sensitivity", name="Motion sensitivity", icon="mdi:tune",
                            section="Detect.MotionDetect", path=(0, "Level"),
                            native_min_value=1, native_max_value=6, native_step=1,
                            entity_category=EntityCategory.CONFIG),
    ConfigNumberDescription(key="tracking_return_time", name="Tracking return time", icon="mdi:timer-outline",
                            section="Detect.DetectTrack", path=("ReturnTime",),
                            native_min_value=10, native_max_value=600, native_step=10,
                            native_unit_of_measurement=UnitOfTime.SECONDS, mode=NumberMode.BOX,
                            entity_category=EntityCategory.CONFIG),
    ConfigNumberDescription(key="white_light_brightness", name="White light brightness", icon="mdi:brightness-6",
                            section="Camera.WhiteLight", path=("Brightness",),
                            native_min_value=0, native_max_value=100, native_step=1,
                            native_unit_of_measurement=PERCENTAGE, entity_category=EntityCategory.CONFIG),
    ConfigNumberDescription(key="white_light_duration", name="White light on-motion duration",
                            icon="mdi:timer-outline", section="Camera.WhiteLight",
                            path=("MoveTrigLight", "Duration"),
                            native_min_value=5, native_max_value=600, native_step=5,
                            native_unit_of_measurement=UnitOfTime.SECONDS, mode=NumberMode.BOX,
                            entity_category=EntityCategory.CONFIG),
]


async def async_setup_entry(hass: HomeAssistant, entry: XMConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(XMConfigNumber(coordinator, d) for d in NUMBERS
                       if coordinator.value(d.section, d.path) is not None)


class XMConfigNumber(XMEntity, NumberEntity):
    entity_description: ConfigNumberDescription

    def __init__(self, coordinator: XMCoordinator, description: ConfigNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        d = self.entity_description
        value = self.coordinator.value(d.section, d.path)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        d = self.entity_description
        await self.coordinator.async_set(d.section, d.path, int(value))
