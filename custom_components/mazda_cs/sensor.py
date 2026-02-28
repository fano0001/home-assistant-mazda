"""Platform for Mazda sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfPressure, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from . import MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN


@dataclass
class MazdaSensorRequiredKeysMixin:
    """Mixin for required keys."""

    # Function to determine the value for this sensor, given the coordinator data
    # and the configured unit system
    value: Callable[[dict[str, Any]], StateType]


@dataclass
class MazdaSensorEntityDescription(
    SensorEntityDescription, MazdaSensorRequiredKeysMixin
):
    """Describes a Mazda sensor entity."""

    # Function to determine whether the vehicle supports this sensor,
    # given the coordinator data
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True


def _fuel_remaining_percentage_supported(data):
    """Determine if fuel remaining percentage is supported."""
    return (data["hasFuel"]) and (
        data["status"]["fuelRemainingPercent"] is not None
    )


def _fuel_distance_remaining_supported(data):
    """Determine if fuel distance remaining is supported."""
    return (data["hasFuel"]) and (
        data["status"]["fuelDistanceRemainingKm"] is not None
    )


def _front_left_tire_pressure_supported(data):
    """Determine if front left tire pressure is supported."""
    return data["status"]["tirePressure"]["frontLeftTirePressurePsi"] is not None


def _front_right_tire_pressure_supported(data):
    """Determine if front right tire pressure is supported."""
    return data["status"]["tirePressure"]["frontRightTirePressurePsi"] is not None


def _rear_left_tire_pressure_supported(data):
    """Determine if rear left tire pressure is supported."""
    return data["status"]["tirePressure"]["rearLeftTirePressurePsi"] is not None


def _rear_right_tire_pressure_supported(data):
    """Determine if rear right tire pressure is supported."""
    return data["status"]["tirePressure"]["rearRightTirePressurePsi"] is not None


def _ev_charge_level_supported(data):
    """Determine if charge level is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["batteryLevelPercentage"] is not None
    )

def _ev_remaining_charging_time_supported(data):
    """Determine if remaining changing time is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["basicChargeTimeMinutes"] is not None
    )

def _ev_quick_charge_time_supported(data):
    """Determine if quick charge time is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["quickChargeTimeMinutes"] is not None
    )

def _ev_remaining_range_supported(data):
    """Determine if remaining range is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["drivingRangeKm"] is not None
    )

def _ev_remaining_bev_range_supported(data):
    """Determine if remaining range bev is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["drivingRangeBevKm"] is not None
    )

def _fuel_distance_remaining_value(data):
    """Get the fuel distance remaining value."""
    return round(data["status"]["fuelDistanceRemainingKm"])


def _odometer_value(data):
    """Get the odometer value."""
    # In order to match the behavior of the Mazda mobile app, we always round down
    return int(data["status"]["odometerKm"])


def _front_left_tire_pressure_value(data):
    """Get the front left tire pressure value."""
    return round(data["status"]["tirePressure"]["frontLeftTirePressurePsi"])


def _front_right_tire_pressure_value(data):
    """Get the front right tire pressure value."""
    return round(data["status"]["tirePressure"]["frontRightTirePressurePsi"])


def _rear_left_tire_pressure_value(data):
    """Get the rear left tire pressure value."""
    return round(data["status"]["tirePressure"]["rearLeftTirePressurePsi"])


def _rear_right_tire_pressure_value(data):
    """Get the rear right tire pressure value."""
    return round(data["status"]["tirePressure"]["rearRightTirePressurePsi"])


def _ev_charge_level_value(data):
    """Get the charge level value."""
    return round(data["evStatus"]["chargeInfo"]["batteryLevelPercentage"])

def _ev_remaining_charging_time_value(data):
    """Get the remaining changing time value."""
    return round(data["evStatus"]["chargeInfo"]["basicChargeTimeMinutes"])

def _ev_remaining_range_value(data):
    """Get the remaining range value."""
    return round(data["evStatus"]["chargeInfo"]["drivingRangeKm"])

def _ev_remaining_range_bev_value(data):
    """Get the remaining range BEV value."""
    return round(data["evStatus"]["chargeInfo"]["drivingRangeBevKm"])


SENSOR_ENTITIES = [
    MazdaSensorEntityDescription(
        key="fuel_remaining_percentage",
        translation_key="fuel_remaining_percentage",
        icon="mdi:gas-station",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_fuel_remaining_percentage_supported,
        value=lambda data: data["status"]["fuelRemainingPercent"],
    ),
    MazdaSensorEntityDescription(
        key="fuel_distance_remaining",
        translation_key="fuel_distance_remaining",
        icon="mdi:gas-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_fuel_distance_remaining_supported,
        value=_fuel_distance_remaining_value,
    ),
    MazdaSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        is_supported=lambda data: data["status"]["odometerKm"] is not None,
        value=_odometer_value,
    ),
    MazdaSensorEntityDescription(
        key="front_left_tire_pressure",
        translation_key="front_left_tire_pressure",
        icon="mdi:tire",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_front_left_tire_pressure_supported,
        value=_front_left_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="front_right_tire_pressure",
        translation_key="front_right_tire_pressure",
        icon="mdi:tire",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_front_right_tire_pressure_supported,
        value=_front_right_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="rear_left_tire_pressure",
        translation_key="rear_left_tire_pressure",
        icon="mdi:tire",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_rear_left_tire_pressure_supported,
        value=_rear_left_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="rear_right_tire_pressure",
        translation_key="rear_right_tire_pressure",
        icon="mdi:tire",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_rear_right_tire_pressure_supported,
        value=_rear_right_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="tire_pressure_timestamp",
        translation_key="tire_pressure_timestamp",
        icon="mdi:tire",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["status"]["tirePressure"]["tirePressureTimestamp"] is not None,
        value=lambda data: data["status"]["tirePressure"]["tirePressureTimestamp"].replace(tzinfo=dt_util.DEFAULT_TIME_ZONE),
    ),
    MazdaSensorEntityDescription(
        key="ev_charge_level",
        translation_key="ev_charge_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_charge_level_supported,
        value=_ev_charge_level_value,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_charging_time",
        translation_key="ev_remaining_charging_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_charging_time_supported,
        value=_ev_remaining_charging_time_value,
    ),
    MazdaSensorEntityDescription(
        key="ev_quick_charge_time",
        translation_key="ev_quick_charge_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_quick_charge_time_supported,
        value=lambda data: round(data["evStatus"]["chargeInfo"]["quickChargeTimeMinutes"]),
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_range",
        translation_key="ev_remaining_range",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_range_supported,
        value=_ev_remaining_range_value,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_range_bev",
        translation_key="ev_remaining_range_bev",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_bev_range_supported,
        value=_ev_remaining_range_bev_value,
    ),
    MazdaSensorEntityDescription(
        key="drive1_drive_time",
        translation_key="drive1_drive_time",
        icon="mdi:car-clock",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data: data["status"]["driveInformation"]["drive1DriveTimeSeconds"] is not None,
        value=lambda data: data["status"]["driveInformation"]["drive1DriveTimeSeconds"],
    ),
    MazdaSensorEntityDescription(
        key="drive1_distance",
        translation_key="drive1_distance",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data: data["status"]["driveInformation"]["drive1DistanceKm"] is not None,
        value=lambda data: data["status"]["driveInformation"]["drive1DistanceKm"],
    ),
    MazdaSensorEntityDescription(
        key="drive1_fuel_efficiency",
        translation_key="drive1_fuel_efficiency",
        icon="mdi:gas-station",
        native_unit_of_measurement="km/L",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data: data["hasFuel"] and data["region"] != "MNAO" and data["status"]["driveInformation"]["drive1FuelEfficiencyKmL"] is not None,
        value=lambda data: data["status"]["driveInformation"]["drive1FuelEfficiencyKmL"],
    ),
    MazdaSensorEntityDescription(
        key="drive1_fuel_consumption",
        translation_key="drive1_fuel_consumption",
        icon="mdi:gas-station",
        native_unit_of_measurement="L/100km",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data: data["hasFuel"] and data["region"] != "MNAO" and data["status"]["driveInformation"]["drive1FuelConsumptionL100km"] is not None,
        value=lambda data: data["status"]["driveInformation"]["drive1FuelConsumptionL100km"],
    ),
    MazdaSensorEntityDescription(
        key="drive1_fuel_efficiency_mpg",
        translation_key="drive1_fuel_efficiency_mpg",
        icon="mdi:gas-station",
        native_unit_of_measurement="MPG",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data: data["hasFuel"] and data["region"] == "MNAO" and data["status"]["driveInformation"]["drive1FuelEfficiencyKmL"] is not None,
        value=lambda data: round(data["status"]["driveInformation"]["drive1FuelEfficiencyKmL"] * 2.35215, 1),
    ),
    MazdaSensorEntityDescription(
        key="drive1_fuel_consumption_gal100mi",
        translation_key="drive1_fuel_consumption_gal100mi",
        icon="mdi:gas-station",
        native_unit_of_measurement="gal/100mi",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data: data["hasFuel"] and data["region"] == "MNAO" and data["status"]["driveInformation"]["drive1FuelConsumptionL100km"] is not None,
        value=lambda data: round(data["status"]["driveInformation"]["drive1FuelConsumptionL100km"] * 0.425144, 2),
    ),
    MazdaSensorEntityDescription(
        key="dr_oil_deteriorate_level",
        translation_key="dr_oil_deteriorate_level",
        icon="mdi:oil",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["hasFuel"] and data["status"]["oilMaintenanceInfo"]["oilHealthPercentage"] is not None,
        value=lambda data: data["status"]["oilMaintenanceInfo"]["oilHealthPercentage"],
    ),
    MazdaSensorEntityDescription(
        key="next_maintenance_distance",
        translation_key="next_maintenance_distance",
        icon="mdi:car-wrench",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["status"]["maintenanceInfo"]["nextMaintenanceDistanceKm"] is not None,
        value=lambda data: data["status"]["maintenanceInfo"]["nextMaintenanceDistanceKm"],
    ),
    MazdaSensorEntityDescription(
        key="oil_level_status",
        translation_key="oil_level_status",
        icon="mdi:oil-level",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["hasFuel"] and data["status"]["oilMaintenanceInfo"]["oilLevelStatus"] is not None,
        value=lambda data: data["status"]["oilMaintenanceInfo"]["oilLevelStatus"],
    ),
    MazdaSensorEntityDescription(
        key="next_oil_change_distance",
        translation_key="next_oil_change_distance",
        icon="mdi:car-wrench",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["hasFuel"] and data["status"]["oilMaintenanceInfo"]["nextOilChangeDistanceKm"] is not None,
        value=lambda data: data["status"]["oilMaintenanceInfo"]["nextOilChangeDistanceKm"],
    ),
    MazdaSensorEntityDescription(
        key="next_scr_maintenance_distance",
        translation_key="next_scr_maintenance_distance",
        icon="mdi:car-wrench",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["isDiesel"] and data["status"]["scrMaintenanceInfo"]["nextScrMaintenanceDistance"] is not None,
        value=lambda data: data["status"]["scrMaintenanceInfo"]["nextScrMaintenanceDistance"],
    ),
    MazdaSensorEntityDescription(
        key="urea_tank_level",
        translation_key="urea_tank_level",
        icon="mdi:car-cruise-control",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["isDiesel"] and data["status"]["scrMaintenanceInfo"]["ureaTankLevel"] is not None,
        value=lambda data: round(data["status"]["scrMaintenanceInfo"]["ureaTankLevel"] / 255 * 100, 1),
    ),
    MazdaSensorEntityDescription(
        key="tns_lamp",
        translation_key="tns_lamp",
        icon="mdi:car-light-dimmed",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["status"]["tnsLight"]["tnsLamp"] is not None,
        value=lambda data: data["status"]["tnsLight"]["tnsLamp"],
    ),
    MazdaSensorEntityDescription(
        key="light_combi_sw_mode",
        translation_key="light_combi_sw_mode",
        icon="mdi:car-light-dimmed",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["status"]["tnsLight"]["lightCombiSWMode"] is not None,
        value=lambda data: data["status"]["tnsLight"]["lightCombiSWMode"],
    ),
    MazdaSensorEntityDescription(
        key="lght_sw_state",
        translation_key="lght_sw_state",
        icon="mdi:car-light-dimmed",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["status"]["tnsLight"]["lghtSwState"] is not None,
        value=lambda data: data["status"]["tnsLight"]["lghtSwState"],
    ),
    MazdaSensorEntityDescription(
        key="engine_state",
        translation_key="engine_state",
        icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["status"]["electricalInformation"]["engineState"] is not None,
        value=lambda data: data["status"]["electricalInformation"]["engineState"],
    ),
    MazdaSensorEntityDescription(
        key="power_control_status",
        translation_key="power_control_status",
        icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["status"]["electricalInformation"]["powerControlStatus"] is not None,
        value=lambda data: data["status"]["electricalInformation"]["powerControlStatus"],
    ),
    MazdaSensorEntityDescription(
        key="pw_sav_mode",
        translation_key="pw_sav_mode",
        icon="mdi:power-sleep",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["status"]["vehicleCondition"]["pwSavMode"] is not None,
        value=lambda data: data["status"]["vehicleCondition"]["pwSavMode"],
    ),
    MazdaSensorEntityDescription(
        key="soc_ecm_a_est",
        translation_key="soc_ecm_a_est",
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_supported=lambda data: data["enableDevSensors"] and data["status"]["batteryStatus"]["socEcmAEst"] is not None,
        value=lambda data: data["status"]["batteryStatus"]["socEcmAEst"],
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

    entities: list[SensorEntity] = []

    for index, data in enumerate(coordinator.data):
        for description in SENSOR_ENTITIES:
            if description.is_supported(data):
                entities.append(
                    MazdaSensorEntity(client, coordinator, index, description)
                )

    async_add_entities(entities)


class MazdaSensorEntity(MazdaEntity, SensorEntity):
    """Representation of a Mazda vehicle sensor."""

    entity_description: MazdaSensorEntityDescription

    def __init__(self, client, coordinator, index, description):
        """Initialize Mazda sensor."""
        super().__init__(client, coordinator, index)
        self.entity_description = description

        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value(self.data)
