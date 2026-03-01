"""Platform for Mazda binary sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN


@dataclass
class MazdaBinarySensorRequiredKeysMixin:
    """Mixin for required keys."""

    # Function to determine the value for this binary sensor, given the coordinator data
    value_fn: Callable[[dict[str, Any]], bool]


@dataclass
class MazdaBinarySensorEntityDescription(
    BinarySensorEntityDescription, MazdaBinarySensorRequiredKeysMixin
):
    """Describes a Mazda binary sensor entity."""

    # Function to determine whether the vehicle supports this binary sensor, given the coordinator data
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True


def _plugged_in_supported(data):
    """Determine if 'plugged in' binary sensor is supported."""
    return (
        data["isElectric"] and data["evStatus"]["chargeInfo"]["pluggedIn"] is not None
    )


BINARY_SENSOR_ENTITIES = [
    MazdaBinarySensorEntityDescription(
        key="driver_door",
        translation_key="driver_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data["status"]["doors"]["driverDoorOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="passenger_door",
        translation_key="passenger_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data["status"]["doors"]["passengerDoorOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_left_door",
        translation_key="rear_left_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data["status"]["doors"]["rearLeftDoorOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_right_door",
        translation_key="rear_right_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data["status"]["doors"]["rearRightDoorOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="trunk",
        translation_key="trunk",
        icon="mdi:car-back",
        device_class=BinarySensorDeviceClass.DOOR,
        is_supported=lambda data: data["hasRearDoor"],
        value_fn=lambda data: data["status"]["doors"]["trunkOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="hood",
        translation_key="hood",
        icon="mdi:car",
        device_class=BinarySensorDeviceClass.DOOR,
        is_supported=lambda data: data["hasBonnet"],
        value_fn=lambda data: data["status"]["doors"]["hoodOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="fuel_lid",
        translation_key="fuel_lid",
        icon="mdi:gas-station",
        device_class=BinarySensorDeviceClass.DOOR,
        is_supported=lambda data: data["hasFuel"] and data["enableWindows"],
        value_fn=lambda data: data["status"]["doors"]["fuelLidOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="sunroof",
        translation_key="sunroof",
        icon="mdi:weather-sunny",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_supported=lambda data: data["enableWindows"],
        value_fn=lambda data: data["status"]["windows"]["sunroofOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="sunroof_tilt",
        translation_key="sunroof_tilt",
        icon="mdi:sun-angle",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_supported=lambda data: data["enableWindows"],
        value_fn=lambda data: data["status"]["windows"]["sunroofTilted"],
    ),
    MazdaBinarySensorEntityDescription(
        key="driver_window",
        translation_key="driver_window",
        icon="mdi:window-open",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_supported=lambda data: data["enableWindows"],
        value_fn=lambda data: data["status"]["windows"]["driverWindowOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="passenger_window",
        translation_key="passenger_window",
        icon="mdi:window-open",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_supported=lambda data: data["enableWindows"],
        value_fn=lambda data: data["status"]["windows"]["passengerWindowOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_left_window",
        translation_key="rear_left_window",
        icon="mdi:window-open",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_supported=lambda data: data["enableWindows"],
        value_fn=lambda data: data["status"]["windows"]["rearLeftWindowOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_right_window",
        translation_key="rear_right_window",
        icon="mdi:window-open",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_supported=lambda data: data["enableWindows"],
        value_fn=lambda data: data["status"]["windows"]["rearRightWindowOpen"],
    ),
    MazdaBinarySensorEntityDescription(
        key="hazard_lights",
        translation_key="hazard_lights",
        icon="mdi:hazard-lights",
        value_fn=lambda data: data["status"]["hazardLightsOn"],
    ),
    MazdaBinarySensorEntityDescription(
        key="scr_maintenance_warning",
        translation_key="scr_maintenance_warning",
        icon="mdi:alert-circle-outline",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["isDiesel"],
        value_fn=lambda data: bool(data["status"]["scrMaintenanceInfo"]["scrMaintenanceWarning"]),
    ),
    MazdaBinarySensorEntityDescription(
        key="ev_plugged_in",
        translation_key="ev_plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        is_supported=_plugged_in_supported,
        value_fn=lambda data: data["evStatus"]["chargeInfo"]["pluggedIn"],
    ),
    MazdaBinarySensorEntityDescription(
        key="ev_battery_heater_on",
        translation_key="ev_battery_heater_on",
        icon="mdi:heat-wave",
        is_supported=lambda data: data["isElectric"] and data["hasBatteryHeater"],
        value_fn=lambda data: data["evStatus"]["chargeInfo"]["batteryHeaterOn"],
    ),
    MazdaBinarySensorEntityDescription(
        key="ev_battery_heater_auto",
        translation_key="ev_battery_heater_auto",
        icon="mdi:heat-wave",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["isElectric"] and data["hasBatteryHeater"],
        value_fn=lambda data: data["evStatus"]["chargeInfo"]["batteryHeaterAuto"],
    ),
    MazdaBinarySensorEntityDescription(
        key="front_left_tire_pressure_warning",
        translation_key="front_left_tire_pressure_warning",
        icon="mdi:car-tire-alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data["status"]["tirePressureWarnings"]["frontLeftTirePressureWarning"],
    ),
    MazdaBinarySensorEntityDescription(
        key="front_right_tire_pressure_warning",
        translation_key="front_right_tire_pressure_warning",
        icon="mdi:car-tire-alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data["status"]["tirePressureWarnings"]["frontRightTirePressureWarning"],
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_left_tire_pressure_warning",
        translation_key="rear_left_tire_pressure_warning",
        icon="mdi:car-tire-alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data["status"]["tirePressureWarnings"]["rearLeftTirePressureWarning"],
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_right_tire_pressure_warning",
        translation_key="rear_right_tire_pressure_warning",
        icon="mdi:car-tire-alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data["status"]["tirePressureWarnings"]["rearRightTirePressureWarning"],
    ),
    MazdaBinarySensorEntityDescription(
        key="tpms_battery_warning",
        translation_key="tpms_battery_warning",
        icon="mdi:car-tire-alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data["status"]["tirePressureWarnings"]["tpmsBatteryWarning"],
    ),
    MazdaBinarySensorEntityDescription(
        key="mnt_tyre_at_flg",
        translation_key="mnt_tyre_at_flg",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"],
        value_fn=lambda data: data["status"]["tirePressureWarnings"]["mntTyreAtFlg"],
    ),
    MazdaBinarySensorEntityDescription(
        key="brake_oil_level_warning",
        translation_key="brake_oil_level_warning",
        icon="mdi:car-brake-fluid-level",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data["status"]["oilMaintenanceInfo"]["brakeOilLevelWarning"],
    ),
    MazdaBinarySensorEntityDescription(
        key="mnt_oil_at_flg",
        translation_key="mnt_oil_at_flg",
        icon="mdi:oil",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["hasFuel"],
        value_fn=lambda data: bool(data["status"]["oilMaintenanceInfo"]["mntOilAtFlg"]),
    ),
    MazdaBinarySensorEntityDescription(
        key="oil_level_warning",
        translation_key="oil_level_warning",
        icon="mdi:oil-level",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["hasFuel"],
        value_fn=lambda data: data["status"]["oilMaintenanceInfo"]["oilLevelWarning"],
    ),
    MazdaBinarySensorEntityDescription(
        key="oil_deteriorate_warning",
        translation_key="oil_deteriorate_warning",
        icon="mdi:oil",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["hasFuel"],
        value_fn=lambda data: data["status"]["oilMaintenanceInfo"]["oilDeteriorateWarning"],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        MazdaBinarySensorEntity(client, coordinator, index, description)
        for index, data in enumerate(coordinator.data)
        for description in BINARY_SENSOR_ENTITIES
        if description.is_supported(data)
    )


class MazdaBinarySensorEntity(MazdaEntity, BinarySensorEntity):
    """Representation of a Mazda vehicle binary sensor."""

    entity_description: MazdaBinarySensorEntityDescription

    def __init__(self, client, coordinator, index, description):
        """Initialize Mazda binary sensor."""
        super().__init__(client, coordinator, index)
        self.entity_description = description

        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        return self.entity_description.value_fn(self.data)
