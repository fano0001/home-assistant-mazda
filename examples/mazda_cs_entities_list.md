# Implemented Entities

## All Vehicles

| Platform | Entity (key) | Entity name | Feature gating |
|---|---|---|---|
| **sensor** | `vehicle_status_timestamp` | Vehicle status last updated | Last time the vehicle sent an update to the server |
| **sensor** | `odometer` | Odometer |  |
| **sensor** | `front_left_tire_pressure` | Front left tire pressure |  |
| **sensor** | `front_right_tire_pressure` | Front right tire pressure |  |
| **sensor** | `rear_left_tire_pressure` | Rear left tire pressure |  |
| **sensor** | `rear_right_tire_pressure` | Rear right tire pressure |  |
| **sensor** | `tire_pressure_timestamp` | Tire pressure last updated |  |
| **sensor** | `drive1_drive_time` | Drive 1 drive time |  |
| **sensor** | `drive1_distance` | Drive 1 distance |  |
| **sensor** | `next_maintenance_distance` | Next maintenance distance |  |
| **sensor** | `light_combi_sw_mode` | Light switch mode |  |
| **sensor** | `soc_ecm_a_est` | 12v battery state of charge | `<= 127`, 127.5 is sent for unsupported vehicles |
| **binary_sensor** | `driver_door` | Driver door |  |
| **binary_sensor** | `passenger_door` | Passenger door |  |
| **binary_sensor** | `rear_left_door` | Rear left door |  |
| **binary_sensor** | `rear_right_door` | Rear right door |  |
| **binary_sensor** | `trunk` | Trunk | `hasRearDoor` |
| **binary_sensor** | `hood` | Hood | `hasBonnet` |
| **binary_sensor** | `hazard_lights` | Hazard lights-on warning |  |
| **binary_sensor** | `front_left_tire_pressure_warning` | Front left tire pressure warning |  |
| **binary_sensor** | `front_right_tire_pressure_warning` | Front right tire pressure warning |  |
| **binary_sensor** | `rear_left_tire_pressure_warning` | Rear left tire pressure warning |  |
| **binary_sensor** | `rear_right_tire_pressure_warning` | Rear right tire pressure warning |  |
| **binary_sensor** | `tpms_battery_warning` | Tire pressure battery |  |
| **binary_sensor** | `tpms_system_fault` | Tire pressure system fault |  |
| **binary_sensor** | `brake_oil_level_warning` | Brake oil level warning |  |
| **binary_sensor** | `pw_sav_mode` | Power saving mode | `!= 2` |
| **binary_sensor** | `tns_lamp` | Exterior lights-on warning |  |
| **binary_sensor** | `health_lights_problem` | Light problem warning | One sensor for 7 bulbs, see entity details for each bulb |
| **lock** | `lock` | Lock |  |
| **device_tracker** | `device_tracker` | Device tracker |  |
| **select** | `flash_light_count` | Flash light count | `hasFlashLight` |
| **switch** | `push_notification_events` | Push notification events |  |
| **button** | `start_engine` | Start engine | `hasRemoteStart` |
| **button** | `stop_engine` | Stop engine | `hasRemoteStart` |
| **button** | `turn_on_hazard_lights` | Turn on hazard lights | `hasFlashLight` |
| **button** | `turn_off_hazard_lights` | Turn off hazard lights | `hasFlashLight` |
| **button** | `flash_lights` | Flash lights | `hasFlashLight` |

## ICE/PHEV Only (hasFuel)

| Platform | Entity (key) | Entity name | Feature gating |
|---|---|---|---|
| **sensor** | `fuel_remaining_percentage` | Fuel remaining percentage |  |
| **sensor** | `fuel_distance_remaining` | Fuel distance remaining |  |
| **sensor** | `drive1_fuel_efficiency` | Drive 1 fuel efficiency | `region != "MNAO"` |
| **sensor** | `drive1_fuel_consumption` | Drive 1 fuel consumption | `region != "MNAO"` |
| **sensor** | `drive1_fuel_efficiency_mpg` | Drive 1 fuel efficiency (MPG) | `region == "MNAO"` |
| **sensor** | `drive1_fuel_consumption_gal100mi` | Drive 1 fuel consumption (gal/100mi) | `region == "MNAO"` |
| **sensor** | `dr_oil_deteriorate_level` | Oil health |  |
| **sensor** | `next_oil_change_distance` | Next oil change distance |  |
| **binary_sensor** | `fuel_lid` | Fuel lid |  |
| **binary_sensor** | `oil_level_warning` | Oil level warning |  |
| **binary_sensor** | `oil_deteriorate_warning` | Oil deterioration warning |  |


## Diesel Only (hasSCR)

| Platform | Entity (key) | Entity name | Feature gating |
|---|---|---|---|
| **sensor** | `next_scr_maintenance_distance` | Next SCR maintenance distance |  |
| **sensor** | `urea_tank_level` | Urea tank level |  |
| **binary_sensor** | `scr_maintenance_warning` | SCR maintenance warning |  |

## EV/PHEV Only (isElectric)

| Platform | Entity (key) | Entity name | Feature gating |
|---|---|---|---|
| **sensor** | `ev_charge_level` | Charge level |  |
| **sensor** | `ev_remaining_charging_time` | Remaining charging time (AC) |  |
| **sensor** | `ev_quick_charge_time` | Remaining quick charge time |  |
| **sensor** | `ev_remaining_range` | Remaining range |  |
| **sensor** | `ev_remaining_range_bev` | Remaining range BEV |  |
| **binary_sensor** | `ev_plugged_in` | Plugged in |  |
| **binary_sensor** | `ev_battery_heater_on` | Battery heater | `hasBatteryHeater` |
| **binary_sensor** | `ev_battery_heater_auto` | Battery heater auto | `hasBatteryHeater` |
| **climate** | `climate` | Climate |  |
| **switch** | `charging` | Charging |  |
| **button** | `refresh_vehicle_status` | Refresh status | `isElectric` |

## Development Entities (enableDevSensors)

| Platform | Entity (key) | Entity name | Feature gating |
|---|---|---|---|
| **switch** | `enable_dev_sensors` | δ \| Development sensors |  |
| **sensor** | `oil_level_status` | δ \| OilLevelStatusMonitor | `hasFuel` |
| **sensor** | `lght_sw_state` | δ \| LghtSwState |  |
| **sensor** | `engine_state` | δ \| EngineState |  |
| **sensor** | `power_control_status` | δ \| PowerControlStatus |  |
| **binary_sensor** | `mnt_tyre_at_flg` | δ \| MntTyreAtFlg |  |
| **binary_sensor** | `mnt_oil_at_flg` | δ \| MntOilAtFlg | `hasFuel` |
| **switch** | `enable_windows` | δ \| Window sensors | **Window keys** are of unknown purpose with no known mobile app usage. Current hypothesis is they are related to security alerts. |
| **binary_sensor** | `sunroof` | Sunroof | `enableWindows` |
| **binary_sensor** | `sunroof_tilt` | Sunroof tilt | `enableWindows` |
| **binary_sensor** | `driver_window` | Driver window | `enableWindows` |
| **binary_sensor** | `passenger_window` | Passenger window | `enableWindows` |
| **binary_sensor** | `rear_left_window` | Rear left window | `enableWindows` |
| **binary_sensor** | `rear_right_window` | Rear right window | `enableWindows` |


