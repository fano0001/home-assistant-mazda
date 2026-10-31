"""Tests for the vehicle home-screen image (``junction/getHomeBgImages/v4``).

The endpoint lives on the legacy Kintaro host, not the MC host the rest of the
client talks to, so these cover both the legacy ``Connection`` config and the
client-layer parsing of the image list, plus the image/select entity pair.
"""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant, State
import pytest
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.mazda_cs import bg_image_options
from custom_components.mazda_cs.image import MazdaVehicleImage
from custom_components.mazda_cs.pymazda.client import Client
from custom_components.mazda_cs.pymazda.connection import (
    LEGACY_REGION_CONFIG,
    REGION_CONFIG,
    SHA256_CERT_SIG,
    SIGNATURE_MD5,
    Connection,
)
from custom_components.mazda_cs.pymazda.controller import Controller
from custom_components.mazda_cs.pymazda.exceptions import MazdaSessionExpiredException
from custom_components.mazda_cs.select import MazdaVehicleImageSelect

VEHICLE = {
    "vin": "JM1TESTVIN",
    "id": 1,
    "nickname": "",
    "modelYear": "2024",
    "carlineName": "MAZDA3 HB",
}
IMAGES = [
    {"name": "MAZDA3 HB=01.jpg", "url": "https://img.test/01.jpg"},
    {"name": "MAZDA3 HB=02.jpg", "url": "https://img.test/02.jpg"},
]
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _make_client() -> Client:
    """Build a Client whose controller is mocked out (no network, no attach)."""
    client = Client(
        user_sub="test-sub",
        region="MNAO",
        access_token_provider=AsyncMock(return_value="token"),
        # Supplied so Connection does not open a real aiohttp session it never closes.
        websession=AsyncMock(),
    )
    client.controller = AsyncMock()
    return client


@pytest.mark.parametrize("region", sorted(REGION_CONFIG))
def test_legacy_connection_uses_kintaro_config(region) -> None:
    """A legacy connection swaps host, app code and cert sig; headers stay regional."""
    mc = Connection("test-sub", region, AsyncMock(), websession=AsyncMock())
    legacy = Connection(
        "test-sub", region, AsyncMock(), websession=AsyncMock(), legacy=True
    )

    assert legacy.base_url == LEGACY_REGION_CONFIG[region]["base_url"]
    assert legacy.app_code == LEGACY_REGION_CONFIG[region]["app_code"]
    assert legacy.cert_sig == SIGNATURE_MD5
    assert mc.cert_sig == SHA256_CERT_SIG
    assert legacy.region_header == mc.region_header
    assert legacy.locale == mc.locale
    assert legacy.base_api_device_id == mc.base_api_device_id
    assert legacy.device_session_id is None


def test_controller_legacy_connection_shares_session_and_never_attaches() -> None:
    """The Kintaro connection reuses the HTTP session and has no re-attach hook."""
    attach = AsyncMock()
    controller = Controller("test-sub", "MNAO", AsyncMock(), attach, AsyncMock())

    assert controller.legacy_connection._session is controller.connection._session
    assert controller.legacy_connection.session_refresh_provider is None
    assert controller.connection.session_refresh_provider is attach


async def test_legacy_connection_does_not_retry_600100() -> None:
    """Without a session_refresh_provider a 600100 is raised, not retried."""
    legacy = Connection(
        "test-sub", "MNAO", AsyncMock(), websession=AsyncMock(), legacy=True
    )
    send = AsyncMock(side_effect=MazdaSessionExpiredException("conflict"))
    legacy._Connection__send_api_request = send

    with pytest.raises(MazdaSessionExpiredException):
        await legacy.api_request("POST", "junction/x", needs_keys=False)
    assert send.await_count == 1


@pytest.mark.parametrize(
    ("model_code4", "sent"),
    [("AB12", "AB12"), (None, "0000"), ("", "0000"), ("ABC", "0000")],
)
async def test_get_home_bg_images_model_code_fallback(model_code4, sent) -> None:
    """Missing or malformed modelCode4 falls back to "0000", like the app."""
    client = _make_client()
    client.controller.get_home_bg_images.return_value = {"images": []}

    await client.get_home_bg_images(model_code4)

    client.controller.get_home_bg_images.assert_awaited_once_with(sent)


async def test_get_home_bg_images_drops_entries_without_url() -> None:
    """Entries with no URL are skipped; name may be None."""
    client = _make_client()
    client.controller.get_home_bg_images.return_value = {
        "images": [
            {"url": "https://a", "name": "front"},
            {"url": None, "name": "broken"},
            {"name": "missing"},
            {"url": "https://b"},
        ]
    }

    assert await client.get_home_bg_images("AB12") == [
        {"name": "front", "url": "https://a"},
        {"name": None, "url": "https://b"},
    ]


async def test_get_home_bg_images_null_list() -> None:
    """``{"images": null}`` yields an empty list."""
    client = _make_client()
    client.controller.get_home_bg_images.return_value = {"images": None}

    assert await client.get_home_bg_images("AB12") == []


def test_home_bg_image_selection_round_trip() -> None:
    """The selected option label is stored per vehicle."""
    client = _make_client()

    assert client.get_home_bg_image(1) is None
    client.set_home_bg_image(1, "front")
    assert client.get_home_bg_image(1) == "front"
    assert client.get_home_bg_image(2) is None


def test_bg_image_options_dedupes_and_fills_missing_names() -> None:
    """Missing names become "Image n"; duplicates get a numeric suffix."""
    images = [
        {"name": "front", "url": "u1"},
        {"name": None, "url": "u2"},
        {"name": "front", "url": "u3"},
        {"name": "front (2)", "url": "u4"},
    ]

    assert bg_image_options(images) == {
        "front": "u1",
        "Image 2": "u2",
        "front (2)": "u3",
        "front (2) (2)": "u4",
    }
    assert bg_image_options(None) == {}


@pytest.mark.parametrize(
    ("name", "label"),
    [
        ("MAZDA3 HB=01.jpg", "Mazda3 HB 01"),
        ("MAZDA CX-5=02.JPG", "Mazda CX-5 02"),
        ("CX-50 = 03.png", "CX-50 03"),
        ("MX-5 2.0=04", "MX-5 2.0 04"),
        (".jpg", "Image 1"),
    ],
)
def test_bg_image_options_normalizes_server_filenames(name, label) -> None:
    """Server filenames lose the extension and "=", and MAZDA becomes Mazda."""
    assert list(bg_image_options([{"name": name, "url": "u"}])) == [label]


class _ImageCoordinator:
    """Minimal stand-in for the image DataUpdateCoordinator."""

    def __init__(self, data) -> None:
        self.data = data
        self._listeners = []

    def async_add_listener(self, update_callback, context=None):
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    def push(self, data) -> None:
        self.data = data
        for update_callback in list(self._listeners):
            update_callback()


def _vehicle_coordinator() -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = [VEHICLE]
    coordinator.last_update_success = True
    return coordinator


async def _add_entities(hass: HomeAssistant, image_data):
    """Create, wire up and add the image + select entities for one vehicle."""
    client = _make_client()
    coordinator = _vehicle_coordinator()
    image_coordinator = _ImageCoordinator(image_data)

    image = MazdaVehicleImage(hass, client, coordinator, image_coordinator, 0)
    select = MazdaVehicleImageSelect(client, coordinator, image_coordinator, 0)
    for entity, entity_id in (
        (image, "image.vehicle_image"),
        (select, "select.vehicle_image"),
    ):
        entity.hass = hass
        entity.entity_id = entity_id
        entity.async_write_ha_state = MagicMock()
    await image.async_added_to_hass()
    await select.async_added_to_hass()
    return image, select, image_coordinator


async def test_entities_default_to_first_image(hass: HomeAssistant) -> None:
    """With no saved selection, both entities show the first image."""
    image, select, _ = await _add_entities(hass, [IMAGES])

    assert select.options == ["Mazda3 HB 01", "Mazda3 HB 02"]
    assert select.current_option == "Mazda3 HB 01"
    assert image.image_url == "https://img.test/01.jpg"
    assert image.available
    assert image.extra_state_attributes["selected"] == "Mazda3 HB 01"


async def test_restored_option_applied_when_data_arrives(hass: HomeAssistant) -> None:
    """A restored selection waits for image data, then the image follows it."""
    mock_restore_cache(hass, (State("select.vehicle_image", "Mazda3 HB 02"),))
    image, select, image_coordinator = await _add_entities(hass, None)

    assert not select.available
    assert not image.available

    image_coordinator.push([IMAGES])

    assert select.current_option == "Mazda3 HB 02"
    assert image.image_url == "https://img.test/02.jpg"


async def test_restored_option_no_longer_offered_falls_back(
    hass: HomeAssistant,
) -> None:
    """A restored label the server stopped offering falls back to the first image."""
    mock_restore_cache(hass, (State("select.vehicle_image", "gone.jpg"),))
    image, select, _ = await _add_entities(hass, [IMAGES])

    assert select.current_option == "Mazda3 HB 01"
    assert image.image_url == "https://img.test/01.jpg"


async def test_image_cache_reset_only_when_url_changes(hass: HomeAssistant) -> None:
    """Refreshing with the same URL keeps the cached image; a new selection drops it."""
    image, select, image_coordinator = await _add_entities(hass, [IMAGES])
    first_updated = image.image_last_updated
    image._cached_image = MagicMock()

    image_coordinator.push([list(IMAGES)])
    assert image._cached_image is not None
    assert image.image_last_updated == first_updated

    await select.async_select_option("Mazda3 HB 02")
    assert image.image_url == "https://img.test/02.jpg"
    assert image._cached_image is None
    assert image.image_last_updated is not None


async def test_image_type_sniffed_from_bytes(hass: HomeAssistant) -> None:
    """Mazda's S3 serves application/octet-stream; the JPEG is still accepted."""
    image, _, _ = await _add_entities(hass, [IMAGES])
    response = MagicMock(
        content=JPEG_BYTES, headers={"content-type": "application/octet-stream"}
    )
    image._fetch_url = AsyncMock(return_value=response)

    assert await image.async_image() == JPEG_BYTES
    assert image.content_type == "image/jpeg"


async def test_image_with_unknown_bytes_is_rejected(hass: HomeAssistant) -> None:
    """Bytes that are not a known image type yield no image."""
    image, _, _ = await _add_entities(hass, [IMAGES])
    response = MagicMock(
        content=b"<html>", headers={"content-type": "application/octet-stream"}
    )
    image._fetch_url = AsyncMock(return_value=response)

    assert await image.async_image() is None
