"""Polling coordinator holding the camera's config sections and clock offset."""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import XMAuthError, XMCamera, XMError
from .const import CLOCK_TOLERANCE_SECONDS, CONF_SYNC_TIME, DOMAIN, SCAN_INTERVAL_SECONDS, SECTIONS

_LOGGER = logging.getLogger(__name__)

type Path = tuple[str | int, ...]


class XMCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: XMCamera, info: dict[str, Any]) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {api.host}",
                         update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS))
        self.api = api
        self.info = info
        self.serial: str = info["SerialNo"]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data: dict[str, Any] = {}
            for name in SECTIONS:
                try:
                    data[name] = await self.api.get_config(name)
                except XMAuthError:
                    raise
                except XMError as err:
                    _LOGGER.debug("Section %s unavailable: %s", name, err)
            data["clock_offset"] = await self._check_clock()
            return data
        except XMAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except XMError as err:
            raise UpdateFailed(str(err)) from err

    async def _check_clock(self) -> float:
        """Seconds the camera clock is ahead of Home Assistant; corrects it when allowed."""
        now = dt_util.now().replace(tzinfo=None)
        offset = (await self.api.get_time() - now).total_seconds()
        if abs(offset) > CLOCK_TOLERANCE_SECONDS and self.config_entry.options.get(CONF_SYNC_TIME, True):
            _LOGGER.info("Camera %s clock off by %.0f s, setting it", self.api.host, offset)
            await self.api.set_time(dt_util.now().replace(tzinfo=None))
            offset = (await self.api.get_time() - dt_util.now().replace(tzinfo=None)).total_seconds()
        return round(offset)

    def value(self, section: str, path: Path) -> Any:
        node = (self.data or {}).get(section)
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return None
        return node

    async def async_set(self, section: str, path: Path, value: Any) -> None:
        """Read-modify-write one field of a section and publish the result without waiting for a poll."""
        try:
            current = copy.deepcopy(await self.api.get_config(section))
            node = current
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            await self.api.set_config(section, current)
        except (XMError, KeyError, IndexError, TypeError) as err:
            raise HomeAssistantError(f"Could not change {section}: {err}") from err
        self.async_set_updated_data({**self.data, section: current})


@dataclass
class XMData:
    coordinator: XMCoordinator


type XMConfigEntry = ConfigEntry[XMData]
