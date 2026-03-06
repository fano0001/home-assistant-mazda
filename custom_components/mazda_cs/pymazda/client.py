import asyncio  # noqa: D100
import datetime
import json
import logging

from .controller import Controller
from .exceptions import MazdaConfigException


def _build_tpms_timestamp(tpms: dict):
    """Build a naive local datetime from TPMS display date/time fields, or None if unavailable."""
    try:
        return datetime.datetime(
            tpms["TPrsDispYear"],
            tpms["TPrsDispMonth"],
            tpms["TPrsDispDate"],
            tpms["TPrsDispHour"],
            tpms["TPrsDispMinute"],
        )
    except (KeyError, TypeError, ValueError):
        return None


class Client:  # noqa: D101
    def __init__(  # noqa: D107
        self, email, region, access_token_provider, websession=None, use_cached_vehicle_list=False
    ):
        if email is None or len(email) == 0:
            raise MazdaConfigException("Invalid or missing email address")

        self.controller = Controller(email, region, access_token_provider, session_refresh_provider=self.attach, websession=websession)
        self._region = region
        self._use_cached_vehicle_list = use_cached_vehicle_list
        self._cached_vehicle_list = None
        self._cached_state = {}
        self._session_id = None
        self._flash_light_counts: dict[int, int] = {}  # vehicle_id → CarFinderParameter (0/1/2)

    # Per-region locale and country code for the attach call, unsure if these are necessary
    _REGION_ATTACH_PARAMS = {
        "MNAO": ("en-US", "US"),
        "MCI":  ("en-CA", "CA"),
        "MME":  ("en-GB", "GB"),
        "MJO":  ("ja-JP", "JP"),
        "MA":   ("en-AU", "AU"),
    }

    async def attach(self):  # noqa: D102
        """Register device session. Call once after authentication before other API calls."""
        locale, country = self._REGION_ATTACH_PARAMS.get(self._region, ("en-US", "US"))
        response = await self.controller.attach(locale, country)
        if response and response.get("data"):
            session_id = response["data"].get("userinfo", {}).get("sessionId")
            if session_id:
                self._session_id = session_id
                self.controller.connection.device_session_id = session_id
        return response

    async def detach(self):  # noqa: D102
        """Deregister device session. Call on integration unload."""
        if self._session_id:
            await self.controller.detach(self._session_id)
            self._session_id = None
            self.controller.connection.device_session_id = None

    async def get_vehicles(self):  # noqa: D102
        if self._use_cached_vehicle_list and self._cached_vehicle_list is not None:
            return self._cached_vehicle_list

        vec_base_infos_response = await self.controller.get_vec_base_infos()

        vehicles = []
        for i, current_vec_base_info in enumerate(
            vec_base_infos_response.get("vecBaseInfos")
        ):
            current_vehicle_flags = vec_base_infos_response.get("vehicleFlags")[i]

            # Ignore vehicles which are not enrolled in Mazda Connected Services
            if current_vehicle_flags.get("vinRegistStatus") != 3:
                continue

            other_veh_info = json.loads(
                current_vec_base_info.get("Vehicle").get("vehicleInformation")
            )

            nickname = await self.controller.get_nickname(
                current_vec_base_info.get("vin")
            )

            vehicle = {
                "vin": current_vec_base_info.get("vin"),
                "id": current_vec_base_info.get("Vehicle", {})
                .get("CvInformation", {})
                .get("internalVin"),
                "nickname": nickname,
                "carlineCode": other_veh_info.get("OtherInformation", {}).get(
                    "carlineCode"
                ),
                "carlineName": other_veh_info.get("OtherInformation", {}).get(
                    "carlineName"
                ),
                "modelYear": other_veh_info.get("OtherInformation", {}).get(
                    "modelYear"
                ),
                "modelCode": other_veh_info.get("OtherInformation", {}).get(
                    "modelCode"
                ),
                "modelName": other_veh_info.get("OtherInformation", {}).get(
                    "modelName"
                ),
                "automaticTransmission": other_veh_info.get("OtherInformation", {}).get(
                    "transmissionType"
                )
                == "A",
                "interiorColorCode": other_veh_info.get("OtherInformation", {}).get(
                    "interiorColorCode"
                ),
                "interiorColorName": other_veh_info.get("OtherInformation", {}).get(
                    "interiorColorName"
                ),
                "exteriorColorCode": other_veh_info.get("OtherInformation", {}).get(
                    "exteriorColorCode"
                ),
                "exteriorColorName": other_veh_info.get("OtherInformation", {}).get(
                    "exteriorColorName"
                ),
                "isPHEV": current_vec_base_info.get("phevFlg") == 1,
                "hasSCR": current_vec_base_info.get("scrFlg") == 1,
                "isElectric": current_vec_base_info.get("econnectType", 0) == 1,
                "hasFuel": other_veh_info.get("CVServiceInformation", {}).get("fuelType", "00") != "05",
                "hasRangeExtender": current_vec_base_info.get("rexFlg") == 1,
                "hasRemoteStart": current_vec_base_info.get("remoteEngineStartFlg") == 1,
                "hasBatteryHeater": current_vec_base_info.get("batteryHeaterFlg") == 1,
                "hasFlashLight": current_vec_base_info.get("flashLightFlg") == 1,
                "hasBonnet": current_vec_base_info.get("bonnetOpenFlg") == 1,
                "hasRearDoor": current_vec_base_info.get("rearDoorOpenFlg") == 1,
            }

            vehicles.append(vehicle)

        if self._use_cached_vehicle_list:
            self._cached_vehicle_list = vehicles
        return vehicles

    async def get_vehicle_status(self, vehicle_id):  # noqa: D102
        vehicle_status_response = await self.controller.get_vehicle_status(vehicle_id)

        alert_info = vehicle_status_response.get("alertInfos")[0]
        remote_info = vehicle_status_response.get("remoteInfos")[0]

        latitude = remote_info.get("PositionInfo", {}).get("Latitude")
        if latitude is not None:
            latitude = latitude * (
                -1
                if remote_info.get("PositionInfo", {}).get("LatitudeFlag") == 1
                else 1
            )
        longitude = remote_info.get("PositionInfo", {}).get("Longitude")
        if longitude is not None:
            longitude = longitude * (
                1
                if remote_info.get("PositionInfo", {}).get("LongitudeFlag") == 1
                else -1
            )

        vehicle_status = {
            "lastUpdatedTimestamp": alert_info.get("OccurrenceDate"),
            "latitude": latitude,
            "longitude": longitude,
            "positionTimestamp": remote_info.get("PositionInfo", {}).get(
                "AcquisitionDatetime"
            ),
            "fuelRemainingPercent": remote_info.get("ResidualFuel", {}).get(
                "FuelSegementDActl"
            ),
            "fuelDistanceRemainingKm": remote_info.get("ResidualFuel", {}).get(
                "RemDrvDistDActlKm"
            ),
            "odometerKm": remote_info.get("DriveInformation", {}).get("OdoDispValue"),
            "doors": {
                "driverDoorOpen": alert_info.get("Door", {}).get("DrStatDrv") == 1,
                "passengerDoorOpen": alert_info.get("Door", {}).get("DrStatPsngr") == 1,
                "rearLeftDoorOpen": alert_info.get("Door", {}).get("DrStatRl") == 1,
                "rearRightDoorOpen": alert_info.get("Door", {}).get("DrStatRr") == 1,
                "trunkOpen": alert_info.get("Door", {}).get("DrStatTrnkLg") == 1,
                "hoodOpen": alert_info.get("Door", {}).get("DrStatHood") == 1,
                "fuelLidOpen": alert_info.get("Door", {}).get("FuelLidOpenStatus") == 1,
                # Not yet integrated: doorOpenWarning
                "doorOpenWarning": alert_info.get("Door", {}).get("DrOpnWrn") == 1, 
            },
            # LockLinkSw = physical lock linkage rod position switch per door.
            # Reads mechanical position, not commanded state — front/rear may differ
            # at rest due to door design differences (rear doors have child lock linkage).
            "doorLocks": {
                "driverDoorUnlocked": alert_info.get("Door", {}).get("LockLinkSwDrv")
                == 1,
                "passengerDoorUnlocked": alert_info.get("Door", {}).get(
                    "LockLinkSwPsngr"
                )
                == 1,
                "rearLeftDoorUnlocked": alert_info.get("Door", {}).get("LockLinkSwRl")
                == 1,
                "rearRightDoorUnlocked": alert_info.get("Door", {}).get("LockLinkSwRr")
                == 1,
                "allDoorsLockedSignal": alert_info.get("Door", {}).get("AllDrSwSignal") == 1,
            },
            "windows": {
                "driverWindowOpen": alert_info.get("Pw", {}).get("PwPosDrv") == 1,
                "passengerWindowOpen": alert_info.get("Pw", {}).get("PwPosPsngr") == 1,
                "rearLeftWindowOpen": alert_info.get("Pw", {}).get("PwPosRl") == 1,
                "rearRightWindowOpen": alert_info.get("Pw", {}).get("PwPosRr") == 1,
                "sunroofOpen": alert_info.get("Door", {}).get("SrSlideSignal") == 1,
                "sunroofTilted": alert_info.get("Door", {}).get("SrTiltSignal") == 1,
            },
            # SeatBeltInformation — not yet integrated as sensors
            "seatBeltInformation": {
                "seatBeltWrnDRq": remote_info.get("SeatBeltInformation", {}).get("SeatBeltWrnDRq"),
                "firstRowBuckleDriver": remote_info.get("SeatBeltInformation", {}).get("FirstRowBuckleDriver"),
                "firstRowBucklePsngr": remote_info.get("SeatBeltInformation", {}).get("FirstRowBucklePsngr"),
                "ocsStatus": remote_info.get("SeatBeltInformation", {}).get("OCSStatus"),
                "seatBeltStatDActl": remote_info.get("SeatBeltInformation", {}).get("SeatBeltStatDActl"),
                "rlOcsStatDActl": remote_info.get("SeatBeltInformation", {}).get("RLOCSStatDActl"),
                "rcOcsStatDActl": remote_info.get("SeatBeltInformation", {}).get("RCOCSStatDActl"),
                "rrOcsStatDActl": remote_info.get("SeatBeltInformation", {}).get("RROCSStatDActl"),
            },
            "hazardLightsOn": alert_info.get("HazardLamp", {}).get("HazardSw") == 1,
            "tnsLight": {
                "tnsLamp": alert_info.get("TnsLight", {}).get("TnsLamp"),
                "lightCombiSWMode": alert_info.get("TnsLight", {}).get("LightCombiSWMode"),
                "lghtSwState": alert_info.get("TnsLight", {}).get("LghtSwState"),
            },
            "tirePressure": {
                "frontLeftTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                    "FLTPrsDispPsi"
                ),
                "frontRightTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                    "FRTPrsDispPsi"
                ),
                "rearLeftTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                    "RLTPrsDispPsi"
                ),
                "rearRightTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                    "RRTPrsDispPsi"
                ),
                "tirePressureTimestamp": _build_tpms_timestamp(
                    remote_info.get("TPMSInformation", {})
                ),
            },
            "tirePressureWarnings": {
                # TPMS Status not implemented / redundant with individual warnings
                "tpmsStatus": remote_info.get("TPMSInformation", {}).get("TPMSStatus") == 1,
                "frontLeftTirePressureWarning": remote_info.get("TPMSInformation", {}).get("FLTyrePressWarn") == 1,
                "frontRightTirePressureWarning": remote_info.get("TPMSInformation", {}).get("FRTyrePressWarn") == 1,
                "rearLeftTirePressureWarning": remote_info.get("TPMSInformation", {}).get("RLTyrePressWarn") == 1,
                "rearRightTirePressureWarning": remote_info.get("TPMSInformation", {}).get("RRTyrePressWarn") == 1,
                "tpmsBatteryWarning": remote_info.get("TPMSInformation", {}).get("TPMSSystemFlt") == 1,
                "mntTyreAtFlg": remote_info.get("TPMSInformation", {}).get("MntTyreAtFlg") == 1,
            },
            "driveInformation": {
                "drive1DriveTimeSeconds": remote_info.get("DriveInformation", {}).get("Drv1DrvTm"),
                "drive1DistanceKm": remote_info.get("DriveInformation", {}).get("Drv1Distnc"),
                "drive1FuelEfficiencyKmL": remote_info.get("DriveInformation", {}).get("Drv1AvlFuelE"),
                "drive1FuelConsumptionL100km": remote_info.get("DriveInformation", {}).get("Drv1AvlFuelG"),
            },
            "oilMaintenanceInfo": {
                "nextOilChangeDistanceKm": remote_info.get("OilMntInformation", {}).get("RemOilDistK"),
                "mntOilAtFlg": remote_info.get("OilMntInformation", {}).get("MntOilAtFlg"),
                "oilDeteriorateWarning": remote_info.get("OilMntInformation", {}).get("OilDeteriorateWarning") == 1,
                "oilHealthPercentage": remote_info.get("OilMntInformation", {}).get("DROilDeteriorateLevel"),
                "mntOilLvlAtFlg": remote_info.get("OilMntInformation", {}).get("MntOilLvlAtFlg"),  # not yet implemented
                "brakeOilLevelWarning": remote_info.get("OilMntInformation", {}).get("OilLevelSensWarnBRq") == 1,
                "oilLevelWarning": remote_info.get("OilMntInformation", {}).get("OilLevelWarning") == 1,
                "oilLevelStatus": remote_info.get("OilMntInformation", {}).get("OilLevelStatusMonitor"),
            },
            "scrMaintenanceInfo": {
                "scrMaintenanceWarning": remote_info.get("MntSCRInformation", {}).get("MntSCRAtFlg"),
                "ureaTankLevel": remote_info.get("MntSCRInformation", {}).get("UreaTankLevel"),
                "nextScrMaintenanceDistance": remote_info.get("MntSCRInformation", {}).get("RemainingMileage"),
            },
            "maintenanceInfo": {
                "nextMaintenanceDistanceKm": remote_info.get("RegularMntInformation", {}).get("RemRegDistKm"),
            },
            "electricalInformation": {
                "engineState": remote_info.get("ElectricalInformation", {}).get("EngineState"),
                "powerControlStatus": remote_info.get("ElectricalInformation", {}).get("PowerControlStatus"),
            },
            "batteryStatus": {
                "socEcmAEst": remote_info.get("BatteryStatus", {}).get("SocEcmAEst"),
            },
            "vehicleCondition": {
                "pwSavMode": alert_info.get("VehicleCondition", {}).get("PwSavMode"),
            },
        }

        door_lock_status = vehicle_status["doorLocks"]
        lock_value = not (
            door_lock_status["driverDoorUnlocked"]
            or door_lock_status["passengerDoorUnlocked"]
            or door_lock_status["rearLeftDoorUnlocked"]
            or door_lock_status["rearRightDoorUnlocked"]
        )

        self.__save_api_value(
            vehicle_id,
            "lock_state",
            lock_value,
            datetime.datetime.strptime(
                vehicle_status["lastUpdatedTimestamp"], "%Y%m%d%H%M%S"
            ).replace(tzinfo=datetime.UTC),
        )

        return vehicle_status

    async def get_ev_vehicle_status(self, vehicle_id):  # noqa: D102
        ev_vehicle_status_response = await self.controller.get_ev_vehicle_status(
            vehicle_id
        )

        result_data = ev_vehicle_status_response.get("resultData")[0]
        vehicle_info = result_data.get("PlusBInformation", {}).get("VehicleInfo", {})
        charge_info = vehicle_info.get("ChargeInfo", {})
        hvac_info = vehicle_info.get("RemoteHvacInfo", {})

        ev_vehicle_status = {
            "lastUpdatedTimestamp": result_data.get("OccurrenceDate"),
            "chargeInfo": {
                "batteryLevelPercentage": charge_info.get("SmaphSOC"),
                "drivingRangeKm": charge_info.get("SmaphRemDrvDistKm"),
                "drivingRangeBevKm": charge_info.get("BatRemDrvDistKm"),
                "pluggedIn": charge_info.get("ChargerConnectorFitting") == 1,
                "charging": charge_info.get("ChargeStatusSub") == 6,
                "basicChargeTimeMinutes": charge_info.get("MaxChargeMinuteAC"),
                "quickChargeTimeMinutes": charge_info.get("MaxChargeMinuteQBC"),
                "batteryHeaterAuto": charge_info.get("CstmzStatBatHeatAutoSW") == 1,
                "batteryHeaterOn": charge_info.get("BatteryHeaterON") == 1,
            },
            "hvacInfo": {
                "hvacOn": hvac_info.get("HVAC") == 1,
                "frontDefroster": hvac_info.get("FrontDefroster") == 1,
                "rearDefroster": hvac_info.get("RearDefogger") == 1,
                "interiorTemperatureCelsius": hvac_info.get("InCarTeDC"),
            },
        }

        self.__save_api_value(
            vehicle_id,
            "hvac_mode",
            ev_vehicle_status["hvacInfo"]["hvacOn"],
            datetime.datetime.strptime(
                ev_vehicle_status["lastUpdatedTimestamp"], "%Y%m%d%H%M%S"
            ).replace(tzinfo=datetime.UTC),
        )

        return ev_vehicle_status

    def get_assumed_lock_state(self, vehicle_id):  # noqa: D102
        return self.__get_assumed_value(
            vehicle_id, "lock_state", datetime.timedelta(seconds=600)
        )

    def get_assumed_hvac_mode(self, vehicle_id):  # noqa: D102
        return self.__get_assumed_value(
            vehicle_id, "hvac_mode", datetime.timedelta(seconds=600)
        )

    def get_assumed_hvac_setting(self, vehicle_id):  # noqa: D102
        return self.__get_assumed_value(
            vehicle_id, "hvac_setting", datetime.timedelta(seconds=600)
        )

    async def turn_on_hazard_lights(self, vehicle_id):  # noqa: D102
        await self.controller.light_on(vehicle_id)

    async def turn_off_hazard_lights(self, vehicle_id):  # noqa: D102
        await self.controller.light_off(vehicle_id)

    _FLASH_COUNT_TO_PARAM = {"2": 1, "10": 2, "30": 3}

    def set_flash_light_count(self, vehicle_id: int, count: str) -> None:  # noqa: D102
        self._flash_light_counts[vehicle_id] = self._FLASH_COUNT_TO_PARAM.get(count, 1)

    async def flash_lights(self, vehicle_id: int) -> None:  # noqa: D102
        car_finder_parameter = self._flash_light_counts.get(vehicle_id, 1)  # default: 10 flashes
        await self.controller.flash_lights(vehicle_id, car_finder_parameter)

    async def unlock_doors(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "lock_state", False)

        await self.controller.door_unlock(vehicle_id)

    async def lock_doors(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "lock_state", True)

        await self.controller.door_lock(vehicle_id)

    async def start_engine(self, vehicle_id):  # noqa: D102
        await self.controller.engine_start(vehicle_id)

    async def stop_engine(self, vehicle_id):  # noqa: D102
        await self.controller.engine_stop(vehicle_id)

    async def send_poi(self, vehicle_id, latitude, longitude, name):  # noqa: D102
        await self.controller.send_poi(vehicle_id, latitude, longitude, name)

    async def start_charging(self, vehicle_id):  # noqa: D102
        await self.controller.charge_start(vehicle_id)

    async def stop_charging(self, vehicle_id):  # noqa: D102
        await self.controller.charge_stop(vehicle_id)

    async def get_hvac_setting(self, vehicle_id):  # noqa: D102
        response = await self.controller.get_hvac_setting(vehicle_id)

        response_hvac_settings = response.get("hvacSettings", {})

        hvac_setting = {
            "temperature": response_hvac_settings.get("Temperature"),
            "temperatureUnit": "C"
            if response_hvac_settings.get("TemperatureType") == 1
            else "F",
            "frontDefroster": response_hvac_settings.get("FrontDefroster") == 1,
            "rearDefroster": response_hvac_settings.get("RearDefogger") == 1,
        }

        self.__save_api_value(vehicle_id, "hvac_setting", hvac_setting)

        return hvac_setting

    async def set_hvac_setting(  # noqa: D102
        self, vehicle_id, temperature, temperature_unit, front_defroster, rear_defroster
    ):
        self.__save_assumed_value(
            vehicle_id,
            "hvac_setting",
            {
                "temperature": temperature,
                "temperatureUnit": temperature_unit,
                "frontDefroster": front_defroster,
                "rearDefroster": rear_defroster,
            },
        )

        await self.controller.set_hvac_setting(
            vehicle_id, temperature, temperature_unit, front_defroster, rear_defroster
        )

    async def turn_on_hvac(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "hvac_mode", True)

        await self.controller.hvac_on(vehicle_id)

    async def turn_off_hvac(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "hvac_mode", False)

        await self.controller.hvac_off(vehicle_id)

    async def refresh_vehicle_status(self, vehicle_id):  # noqa: D102
        await self.controller.refresh_vehicle_status(vehicle_id)

    async def get_inbox_list(self, internal_vin_list, actiontype="001,021,031,033", status=0, limit=100, offset=0):  # noqa: D102
        return await self.controller.get_inbox_list(internal_vin_list, actiontype, status, limit, offset)

    async def poll_remote_service_result(  # noqa: D102
        self, vehicle_id: int, command_utc: datetime.datetime
    ) -> dict | None:
        """Poll inbox for the result of a remote command.

        Checks at 6 s, 18 s, 23 s, 28s, and 40 s after command_utc (typ. 2-4 API calls).
        Returns a result dict on match, or None if no result found within 40 s.
        """
        _LOGGER = logging.getLogger(__name__)
        # Allow 5 s clock-skew buffer; resultId embeds the server-side request timestamp
        cutoff = command_utc - datetime.timedelta(seconds=5)

        loop_start = datetime.datetime.now(datetime.timezone.utc)

        for delay, elapsed in ((6, 6), (12, 18), (5, 23), (5, 28), (12, 40)):  # cumulative waits
            await asyncio.sleep(delay)
            try:
                response = await self.controller.get_inbox_list(
                    [vehicle_id], actiontype="001,019,021", status=0, limit=10
                )
                # Collect entries whose resultId timestamp >= cutoff (oldest-first match)
                # resultId format: "001YYYYMMDDHHMMSS_01" — prefix(3) + timestamp(14) + suffix(3)
                matching = []
                for entry in response.get("InboxInfos", []):
                    result_id = entry.get("resultId", "")
                    if len(result_id) >= 17:
                        try:
                            result_dt = datetime.datetime.strptime(
                                result_id[3:17], "%Y%m%d%H%M%S"
                            ).replace(tzinfo=datetime.timezone.utc)
                            if result_dt >= cutoff:
                                matching.append(entry)
                        except ValueError:
                            pass
                if matching:
                    # List is newest-first; take the oldest (last) to match our command
                    entry = matching[-1]
                    # Re-derive result_dt from the matched entry (loop variable may be stale)
                    # matched_result_id = entry.get("resultId", "")
                    # matched_result_dt = datetime.datetime.strptime(
                    #     matched_result_id[3:17], "%Y%m%d%H%M%S"
                    # ).replace(tzinfo=datetime.timezone.utc)
                    # result_id_delta = (matched_result_dt - loop_start).total_seconds()
                    # push_date_str = entry.get("pushDate", "")
                    # try:
                    #     push_dt = datetime.datetime.strptime(
                    #         push_date_str, "%Y%m%d%H%M%S"
                    #     ).replace(tzinfo=datetime.timezone.utc)
                    #     push_delta = (push_dt - loop_start).total_seconds()
                    #     push_delta_str = f"{push_delta:+.1f}s"
                    # except ValueError:
                    #     push_delta_str = "n/a"
                    # _LOGGER.warning(
                    #     "poll_remote_service_result: match at %ds mark — result_id: %+.1fs from loop start, pushDate: %s from loop start",
                    #     elapsed,
                    #     result_id_delta,
                    #     push_delta_str,
                    # )
                    return {
                        "success": entry.get("messageContents") == "Success",
                        "title": entry.get("messageTitle", ""),
                        "message": entry.get("messageContents", ""),
                        "details": entry.get("messageDetails", ""),
                    }
            except Exception:  # noqa: BLE001
                _LOGGER.debug("poll_remote_service_result: inbox fetch failed (will retry)")

        return None

    async def update_vehicle_nickname(self, vin, new_nickname):  # noqa: D102
        await self.controller.update_nickname(vin, new_nickname)

    async def close(self):  # noqa: D102
        await self.controller.close()

    def __get_assumed_value(self, vehicle_id, key, assumed_state_validity_duration):
        cached_state = self.__get_cached_state(vehicle_id)

        assumed_value_key = "assumed_" + key
        api_value_key = "api_" + key
        assumed_value_timestamp_key = assumed_value_key + "_timestamp"
        api_value_timestamp_key = api_value_key + "_timestamp"

        if assumed_value_key not in cached_state and api_value_key not in cached_state:
            return None

        if assumed_value_key in cached_state and api_value_key not in cached_state:
            return cached_state.get(assumed_value_key)

        if assumed_value_key not in cached_state and api_value_key in cached_state:
            return cached_state.get(api_value_key)

        now_timestamp = datetime.datetime.now(datetime.UTC)

        if (
            assumed_value_timestamp_key in cached_state
            and api_value_timestamp_key in cached_state
            and cached_state.get(assumed_value_timestamp_key)
            > cached_state.get(api_value_timestamp_key)
            and (now_timestamp - cached_state.get(assumed_value_timestamp_key))
            < assumed_state_validity_duration
        ):
            return cached_state.get(assumed_value_key)

        return cached_state.get(api_value_key)

    def __save_assumed_value(self, vehicle_id, key, value, timestamp=None):
        cached_state = self.__get_cached_state(vehicle_id)

        timestamp_value = (
            timestamp if timestamp is not None else datetime.datetime.now(datetime.UTC)
        )

        cached_state["assumed_" + key] = value
        cached_state["assumed_" + key + "_timestamp"] = timestamp_value

    def __save_api_value(self, vehicle_id, key, value, timestamp=None):
        cached_state = self.__get_cached_state(vehicle_id)

        timestamp_value = (
            timestamp if timestamp is not None else datetime.datetime.now(datetime.UTC)
        )

        cached_state["api_" + key] = value
        cached_state["api_" + key + "_timestamp"] = timestamp_value

    def __get_cached_state(self, vehicle_id):
        if vehicle_id not in self._cached_state:
            self._cached_state[vehicle_id] = {}

        return self._cached_state[vehicle_id]
