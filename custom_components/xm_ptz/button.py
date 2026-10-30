"""One-shot camera actions: PTZ steps, tour, clock sync, reboot."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import XMCamera, XMError
from .coordinator import XMConfigEntry, XMCoordinator
from .entity import XMEntity


@dataclass(frozen=True, kw_only=True)
class XMButtonDescription(ButtonEntityDescription):
    press: Callable[[XMCamera], Awaitable[None]]
    refresh: bool = False


def _step(direction: str) -> Callable[[XMCamera], Awaitable[None]]:
    return lambda api: api.ptz_step(direction, 5, 0.5)


BUTTONS = [
    XMButtonDescription(key="ptz_up", name="PTZ up", icon="mdi:arrow-up-bold", press=_step("up")),
    XMButtonDescription(key="ptz_down", name="PTZ down", icon="mdi:arrow-down-bold", press=_step("down")),
    XMButtonDescription(key="ptz_left", name="PTZ left", icon="mdi:arrow-left-bold", press=_step("left")),
    XMButtonDescription(key="ptz_right", name="PTZ right", icon="mdi:arrow-right-bold", press=_step("right")),
    XMButtonDescription(key="zoom_in", name="Zoom in", icon="mdi:magnify-plus", press=_step("zoom_in"),
                        entity_registry_enabled_default=False),
    XMButtonDescription(key="zoom_out", name="Zoom out", icon="mdi:magnify-minus", press=_step("zoom_out"),
                        entity_registry_enabled_default=False),
    XMButtonDescription(key="tour_start", name="Tour start", icon="mdi:rotate-360",
                        press=lambda api: api.tour(True)),
    XMButtonDescription(key="tour_stop", name="Tour stop", icon="mdi:stop", press=lambda api: api.tour(False)),
    XMButtonDescription(key="sync_time", name="Sync clock", icon="mdi:clock-check-outline",
                        entity_category=EntityCategory.CONFIG, refresh=True,
                        press=lambda api: api.set_time(dt_util.now().replace(tzinfo=None))),
    XMButtonDescription(key="reboot", name="Reboot", device_class=ButtonDeviceClass.RESTART,
                        entity_category=EntityCategory.CONFIG, press=lambda api: api.reboot()),
]


async def async_setup_entry(hass: HomeAssistant, entry: XMConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(XMButton(coordinator, d) for d in BUTTONS)


class XMButton(XMEntity, ButtonEntity):
    entity_description: XMButtonDescription

    def __init__(self, coordinator: XMCoordinator, description: XMButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.entity_description.press(self.coordinator.api)
        except XMError as err:
            raise HomeAssistantError(str(err)) from err
        if self.entity_description.refresh:
            await self.coordinator.async_request_refresh()
