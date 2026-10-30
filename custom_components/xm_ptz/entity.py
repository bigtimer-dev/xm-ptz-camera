"""Base entity for the XM camera."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import XMCoordinator


class XMEntity(CoordinatorEntity[XMCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: XMCoordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.info
        self._attr_unique_id = f"{coordinator.serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            manufacturer="Xiongmai",
            model=info.get("DeviceModel"),
            name="XM PTZ Camera",
            serial_number=coordinator.serial,
            sw_version=info.get("SoftWareVersion"),
            configuration_url=f"http://{coordinator.api.host}",
        )
