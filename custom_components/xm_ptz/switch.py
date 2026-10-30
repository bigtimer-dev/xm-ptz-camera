"""On/off settings stored in the camera's config sections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import Path, XMConfigEntry, XMCoordinator
from .entity import XMEntity


@dataclass(frozen=True, kw_only=True)
class ConfigSwitchDescription(SwitchEntityDescription):
    section: str
    path: Path
    on: Any = True
    off: Any = False


SWITCHES = [
    ConfigSwitchDescription(key="motion_detection", name="Motion detection", icon="mdi:motion-sensor",
                            section="Detect.MotionDetect", path=(0, "Enable")),
    ConfigSwitchDescription(key="person_detection", name="Person detection", icon="mdi:account-search",
                            section="Detect.HumanDetection", path=(0, "Enable")),
    ConfigSwitchDescription(key="auto_tracking", name="Auto tracking", icon="mdi:target-account",
                            section="Detect.DetectTrack", path=("Enable",), on=1, off=0),
    ConfigSwitchDescription(key="motion_alarm_output", name="Motion alarm light/output", icon="mdi:alarm-light",
                            section="Detect.MotionDetect", path=(0, "EventHandler", "AlarmOutEnable")),
    ConfigSwitchDescription(key="motion_voice", name="Motion voice warning", icon="mdi:bullhorn",
                            section="Detect.MotionDetect", path=(0, "EventHandler", "VoiceEnable")),
    ConfigSwitchDescription(key="motion_record", name="Record on motion", icon="mdi:record-rec",
                            section="Detect.MotionDetect", path=(0, "EventHandler", "RecordEnable"),
                            entity_category=EntityCategory.CONFIG),
    ConfigSwitchDescription(key="flip", name="Flip image", icon="mdi:flip-vertical",
                            section="Camera.Param", path=(0, "PictureFlip"), on="0x00000001", off="0x00000000",
                            entity_category=EntityCategory.CONFIG),
    ConfigSwitchDescription(key="mirror", name="Mirror image", icon="mdi:flip-horizontal",
                            section="Camera.Param", path=(0, "PictureMirror"), on="0x00000001", off="0x00000000",
                            entity_category=EntityCategory.CONFIG),
]


async def async_setup_entry(hass: HomeAssistant, entry: XMConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(XMConfigSwitch(coordinator, d) for d in SWITCHES
                       if coordinator.value(d.section, d.path) is not None)


class XMConfigSwitch(XMEntity, SwitchEntity):
    entity_description: ConfigSwitchDescription

    def __init__(self, coordinator: XMCoordinator, description: ConfigSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        d = self.entity_description
        value = self.coordinator.value(d.section, d.path)
        return None if value is None else value != d.off

    async def async_turn_on(self, **kwargs: Any) -> None:
        d = self.entity_description
        await self.coordinator.async_set(d.section, d.path, d.on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        d = self.entity_description
        await self.coordinator.async_set(d.section, d.path, d.off)
