import pytest
from homeassistant.core import HomeAssistant
from custom_components.mazda_cs.const import DOMAIN, DATA_COORDINATOR
from custom_components.mazda_cs.diagnostics import async_get_config_entry_diagnostics
from custom_components.mazda_cs.coordinator import MazdaDataCoordinator
from custom_components.mazda_cs.pymazda.api_v2 import MazdaVehicle, MazdaVehicleStatus

@pytest.mark.asyncio
async def test_diagnostics_structure(tmp_path):
    hass = HomeAssistant(config_dir=str(tmp_path))
    coord = MazdaDataCoordinator(hass, email="u@example.com", password="pw", region="MME")
    veh = MazdaVehicle(vin="JMZTEST", id="1", nickname="Test", model_name="MX-30", model_year=2022, raw={"vin":"JMZTEST"})
    coord.vehicles = [veh]
    coord.data = {"status": {"JMZTEST": MazdaVehicleStatus(vin="JMZTEST", battery_percent=80.0, remaining_range_km=150.0, raw={"soc":80})}}

    class _Entry:
        title="u@example.com"
        data={"email":"u@example.com","password":"pw","region":"MME"}
        unique_id="u@example.com_MME"
        entry_id="123"
        def as_dict(self): return {"data": self.data}

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][_Entry.entry_id] = {DATA_COORDINATOR: coord}

    data = await async_get_config_entry_diagnostics(hass, _Entry())
    assert "vehicles" in data and "status" in data
    assert data["config_entry"]["data"]["email"] != "u@example.com"
