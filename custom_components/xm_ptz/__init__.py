"""XM PTZ camera integration (Xiongmai DVRIP protocol on TCP 34567, alarms pushed over the same socket)."""
from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import XMAuthError, XMCamera, XMError
from .const import DOMAIN, EVENT_ALARM, SIGNAL_ALARM
from .coordinator import XMConfigEntry, XMCoordinator, XMData

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: XMConfigEntry) -> bool:
    api = XMCamera(entry.data[CONF_HOST], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD],
                   entry.data[CONF_PORT])
    try:
        info = await api.system_info()
    except XMAuthError as err:
        await api.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except XMError as err:
        await api.close()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = XMCoordinator(hass, entry, api, info)
    entry.async_on_unload(api.close)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = XMData(coordinator)

    @callback
    def on_alarm(alarm: dict) -> None:
        hass.bus.async_fire(EVENT_ALARM, {
            "serial": coordinator.serial,
            "event": alarm.get("Event"),
            "active": alarm.get("Status") == "Start",
            "raw": alarm,
        })
        async_dispatcher_send(hass, SIGNAL_ALARM.format(coordinator.serial), alarm)

    # Alarms subscribe on the next (re)login, which run() keeps alive.
    api.on_alarm = on_alarm
    await api.close()
    entry.async_create_background_task(hass, api.run(), f"{DOMAIN} connection {api.host}")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: XMConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: XMConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
