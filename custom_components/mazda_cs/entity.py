"""Representation of a Mazda entity."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

class MazdaEntity(CoordinatorEntity):
    """Representation of a Mazda entity."""

    def __init__(self, client, coordinator, index):
        """Initialize Mazda entity."""
        super().__init__(coordinator)
        self.client = client
        self.index = index
        self.data = coordinator.data[index]
        self.vin = self.data["vin"]
        self.vehicle_id = self.data["id"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.vin)},
            manufacturer="Mazda",
            name=self.data["nickname"],
            model=self.data["modelName"],
            sw_version=self.data["softwareVersion"],
        )
