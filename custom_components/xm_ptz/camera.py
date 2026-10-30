"""Camera entities (RTSP stream + DVRIP snapshot) and the PTZ / preset / raw actions."""
from __future__ import annotations

import json

import voluptuous as vol

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import XMError
from .const import PTZ_DIRECTIONS
from .coordinator import XMConfigEntry, XMCoordinator
from .entity import XMEntity


async def async_setup_entry(hass: HomeAssistant, entry: XMConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([XMCameraEntity(coordinator, 0), XMCameraEntity(coordinator, 1)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("ptz", {
        vol.Required("direction"): vol.In(PTZ_DIRECTIONS + ["stop"]),
        vol.Optional("speed", default=5): vol.All(vol.Coerce(int), vol.Range(1, 10)),
        vol.Optional("duration", default=0.5): vol.All(vol.Coerce(float), vol.Range(0, 30)),
    }, "async_ptz")
    preset = {vol.Required("preset"): vol.All(vol.Coerce(int), vol.Range(1, 255))}
    platform.async_register_entity_service("goto_preset", preset, "async_goto_preset")
    platform.async_register_entity_service("save_preset", preset, "async_save_preset")
    platform.async_register_entity_service("delete_preset", preset, "async_delete_preset")
    platform.async_register_entity_service("tour", {vol.Required("start"): cv.boolean}, "async_tour")
    platform.async_register_entity_service("get_config", {
        vol.Required("name"): cv.matches_regex(r"^[A-Za-z0-9_.\[\]]+$"),
    }, "async_get_config", supports_response=SupportsResponse.ONLY)
    platform.async_register_entity_service("set_config", {
        vol.Required("name"): cv.matches_regex(r"^[A-Za-z0-9_.\[\]]+$"),
        vol.Required("value"): vol.Any(dict, list, cv.string),
    }, "async_set_config")


class XMCameraEntity(XMEntity, Camera):
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator: XMCoordinator, stream: int) -> None:
        XMEntity.__init__(self, coordinator, f"camera_{stream}")
        Camera.__init__(self)
        self._stream = stream
        self._attr_name = None if stream == 0 else "Sub stream"
        self._attr_entity_registry_enabled_default = stream == 0
        self._last_direction = "left"

    @property
    def api(self):
        return self.coordinator.api

    async def stream_source(self) -> str | None:
        return self.api.rtsp_url(self._stream)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        try:
            return await self.api.snapshot()
        except XMError:
            return None

    async def _run(self, coro) -> None:
        try:
            await coro
        except XMError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_ptz(self, direction: str, speed: int = 5, duration: float = 0.5) -> None:
        if direction == "stop":
            await self._run(self.api.ptz_stop(self._last_direction))
            return
        self._last_direction = direction
        if duration == 0:
            await self._run(self.api.ptz_move(direction, speed))  # keeps moving until "stop"
        else:
            await self._run(self.api.ptz_step(direction, speed, duration))

    async def async_goto_preset(self, preset: int) -> None:
        await self._run(self.api.preset("GotoPreset", preset))

    async def async_save_preset(self, preset: int) -> None:
        await self._run(self.api.preset("SetPreset", preset))

    async def async_delete_preset(self, preset: int) -> None:
        await self._run(self.api.preset("ClearPreset", preset))

    async def async_tour(self, start: bool) -> None:
        await self._run(self.api.tour(start))

    async def async_get_config(self, name: str) -> ServiceResponse:
        try:
            return {"name": name, "value": await self.api.get_config(name)}
        except XMError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_set_config(self, name: str, value) -> None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError as err:
                raise HomeAssistantError(f"value is not JSON: {err}") from err
        await self._run(self.api.set_config(name, value))
        await self.coordinator.async_request_refresh()
