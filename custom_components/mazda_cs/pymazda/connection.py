import asyncio  # noqa: D100
import base64
import hashlib
import json
import logging
import ssl
import time
import uuid
from urllib.parse import urlencode

import aiohttp

from .crypto_utils import (
    decrypt_aes128cbc_buffer_to_str,
    encrypt_aes128cbc_buffer_to_base64_str,
)
from .exceptions import (
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaConfigException,
    MazdaException,
    MazdaRequestInProgressException,
    MazdaSessionExpiredException,
    MazdaTokenExpiredException,
)
from .sensordata.sensor_data_builder import SensorDataBuilder
from .ssl_context_configurator.ssl_context_configurator import SSLContextConfigurator

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.load_default_certs()
ssl_context.set_ciphers("TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA:AES256-SHA")

SSL_SIGNATURE_ALGORITHMS = [
    "ecdsa_secp256r1_sha256",
    "rsa_pss_rsae_sha256",
    "rsa_pkcs1_sha256",
    "ecdsa_secp384r1_sha384",
    "rsa_pss_rsae_sha384",
    "rsa_pkcs1_sha384",
    "rsa_pss_rsae_sha512",
    "rsa_pkcs1_sha512",
    "rsa_pkcs1_sha1",
]
with SSLContextConfigurator(ssl_context, libssl_path="libssl.so.3") as ssl_context_configurator:
    ssl_context_configurator.configure_signature_algorithms(":".join(SSL_SIGNATURE_ALGORITHMS))

# --- iOS app constants (captured from com.mazdausa.mazdaiphone traffic) ---
# IOS_MNAO_APP_CODE = "635529297359258474866"
# IOS_APP_PACKAGE_ID = "com.mazdausa.mazdaiphone"
# IOS_USER_AGENT_BASE_API = "MyMazda-ios/9.0.8"
# IOS_APP_OS = "IOS"
# IOS_APP_VERSION = "9.0.8"
# IOS_SIGN_PACKAGE_ID = unknown  (sign_code may differ from Android's "202406061255295340265")
# IOS_SIGNATURE_MD5 = unknown    (native lib constant in iOS binary not yet extracted)
# IOS_SHA256_CERT_SIG = unknown  (iOS signing cert SHA256, not derivable from Android APK)

# --- Android app constants (confirmed from com.interrait.mymazda 9.0.8 APK) ---
IV = "0102030405060708"
# SIGNATURE_MD5: confirmed from libnativeSKlib.so strings (MD5 of APK signing cert)
SIGNATURE_MD5 = "C383D8C4D279B78130AD52DC71D95CAA"
# SHA256_CERT_SIG: SHA256 of same APK signing cert — used in new MC API (j.f11208e) sign derivation
SHA256_CERT_SIG = "C022C9EE778CF903838F8B9C4B9FF0036A5C516CEFAAD6DC710B717CF97DCFCA"
# SIGN_PACKAGE_ID: Android package name used in key derivation (NOT SDMConfigDataUtil.getSignCode())
# SDMConfigDataUtil.getSignCode() = "202406061255295340265" is used elsewhere, not here
SIGN_PACKAGE_ID = "com.interrait.mymazda"

# REGION_CONFIG app_codes sourced from assets/config/*_core_config.json MC_APP_CODE fields.
# MNAO old API app_code (APP_CODE, j.f11207d, 0cxo7m58.mazda.com): "202007270941270111799"
# cert_sig: new MC API (j.f11208e / hgs2ivna.mazda.com) uses SHA256 path; old API uses MD5 path
REGION_CONFIG = {
    "MNAO": {
        "app_code": "498345786246797888995",   # MC_APP_CODE from MNAO_core_config.json
        "base_url": "https://hgs2ivna.mazda.com/",
        "region_header": "us",
        "cert_sig": SHA256_CERT_SIG,           # new MC API → SHA256 path
    },
    "MCI": {
        "app_code": "498345786246797888995",   # MC_APP_CODE from MCI_core_config.json (same as MNAO)
        "base_url": "https://hgs2ivna.mazda.com/",  # Canada shares MNAO infrastructure
        "region_header": "ca",
        "cert_sig": SHA256_CERT_SIG,
    },
    "MME": {
        "app_code": "365747628595648782737",    # MC_APP_CODE from MME_core_config.json
        "base_url": "https://hgs2iveu.mazda.com/",
        "region_header": "eu",
        "cert_sig": SHA256_CERT_SIG,             # Guess, maybe be different
    },
    "MJO": {
        "app_code": "438849393836584965983",    # MC_APP_CODE from MJO_core_config.json
        "base_url": "https://hgs2ivap.mazda.com/",
        "region_header": "jp",
        "cert_sig": SHA256_CERT_SIG,             # Guess, maybe be different
    },
    "MA": {
        "app_code": "438849393836584965983",    # MC_APP_CODE from MA_core_config.json (same as MJO)
        "base_url": "https://hgs2ivap.mazda.com/",  # Australia shares MJO API infrastructure
        "region_header": "au",
        "cert_sig": SHA256_CERT_SIG,
    },
}
# APP_PACKAGE_ID: Android package name, used in app-unique-id header
APP_PACKAGE_ID = "com.interrait.mymazda"
USER_AGENT_BASE_API = "MyMazda/9.0.8 (Linux; Android 14)"
APP_OS = "ANDROID"
APP_VERSION = "9.0.8"

MAX_RETRIES = 4


class Connection:
    """Main class for handling MyMazda API connection."""

    def __init__(self, email, region, access_token_provider, session_refresh_provider=None, websession=None):  # noqa: D107
        self.email = email
        self.access_token_provider = access_token_provider
        self.session_refresh_provider = session_refresh_provider
        self._refreshing_session = False

        if region in REGION_CONFIG:
            region_config = REGION_CONFIG[region]
            self.app_code = region_config["app_code"]
            self.base_url = region_config["base_url"]
            self.region_header = region_config["region_header"]
            self.cert_sig = region_config["cert_sig"]
        else:
            raise MazdaConfigException("Invalid region")

        self.base_api_device_id = hashlib.sha1(email.encode()).hexdigest()
        self.device_session_id = None  # Set to attach sessionId after successful attach

        self.enc_key = None
        self.sign_key = None

        self.access_token = None

        self.sensor_data_builder = SensorDataBuilder()

        if websession is None:
            self._session = aiohttp.ClientSession()
        else:
            self._session = websession

        self.logger = logging.getLogger(__name__)

    def __get_timestamp_str_ms(self):
        return str(int(round(time.time() * 1000)))

    def __derive_key_material(self, app_code):
        val1 = hashlib.md5((app_code + SIGN_PACKAGE_ID).encode()).hexdigest().upper()
        val2 = hashlib.md5((val1 + self.cert_sig).encode()).hexdigest().lower()
        self.logger.debug("Key derivation: app_code=%s, pkg=%s, cert_sig=%s, val1=%s, val2=%s, dec_key=%s", app_code, SIGN_PACKAGE_ID, self.cert_sig[:8] + "...", val1, val2, val2[4:20])
        return val2

    def __get_decryption_key_from_app_code(self, app_code=None):
        val2 = self.__derive_key_material(app_code or self.app_code)
        return val2[4:20]

    def __get_temporary_sign_key_from_app_code(self, app_code=None):
        val2 = self.__derive_key_material(app_code or self.app_code)
        return val2[20:32] + val2[0:10] + val2[4:6]

    def __get_sign_from_timestamp(self, timestamp, app_code=None):
        if timestamp is None or timestamp == "":
            return ""

        timestamp_extended = (timestamp + timestamp[6:] + timestamp[3:]).upper()

        temporary_sign_key = self.__get_temporary_sign_key_from_app_code(app_code)

        return self.__get_payload_sign(timestamp_extended, temporary_sign_key).upper()

    def __get_sign_from_payload_and_timestamp(self, payload, timestamp):
        if timestamp is None or timestamp == "":
            return ""
        if self.sign_key is None or self.sign_key == "":
            raise MazdaException("Missing sign key")

        return self.__get_payload_sign(
            self.__encrypt_payload_using_key(payload)
            + timestamp
            + timestamp[6:]
            + timestamp[3:],
            self.sign_key,
        )

    def __get_payload_sign(self, encrypted_payload_and_timestamp, sign_key):
        return (
            hashlib.sha256((encrypted_payload_and_timestamp + sign_key).encode())
            .hexdigest()
            .upper()
        )

    def __encrypt_payload_using_key(self, payload):
        if self.enc_key is None or self.enc_key == "":
            raise MazdaException("Missing encryption key")
        if payload is None or payload == "":
            return ""

        return encrypt_aes128cbc_buffer_to_base64_str(
            payload.encode("utf-8"), self.enc_key, IV
        )

    def __decrypt_payload_using_app_code(self, payload, app_code=None):
        buf = base64.b64decode(payload)
        key = self.__get_decryption_key_from_app_code(app_code)
        decrypted = decrypt_aes128cbc_buffer_to_str(buf, key, IV)
        return json.loads(decrypted)

    def __decrypt_payload_using_key(self, payload):
        if self.enc_key is None or self.enc_key == "":
            raise MazdaException("Missing encryption key")

        buf = base64.b64decode(payload)
        decrypted = decrypt_aes128cbc_buffer_to_str(buf, self.enc_key, IV)
        return json.loads(decrypted)

    async def api_request(  # noqa: D102
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
    ):
        return await self.__api_request_retry(
            method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries=0
        )

    async def __api_request_retry(
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
        num_retries=0,
    ):
        if num_retries > MAX_RETRIES:
            raise MazdaException("Request exceeded max number of retries")

        if needs_keys:
            await self.__ensure_keys_present()
        if needs_auth:
            await self.__ensure_token_is_valid()

        retry_message = (
            (" - attempt #" + str(num_retries + 1)) if (num_retries > 0) else ""
        )
        self.logger.debug(
            f"Sending {method} request to {uri}{retry_message}"  # noqa: G004
        )  # noqa: G004

        try:
            return await self.__send_api_request(
                method, uri, query_dict, body_dict, needs_keys, needs_auth
            )
        except MazdaAPIEncryptionException:
            if "checkVersion" in uri:
                raise MazdaException("checkVersion rejected by server (wrong SIGNATURE_MD5 or app_code). Cannot retrieve encryption keys.")
            self.logger.info(
                "Server reports request was not encrypted properly. Retrieving new encryption keys."
            )
            await self.__retrieve_keys()
            return await self.__api_request_retry(
                method,
                uri,
                query_dict,
                body_dict,
                needs_keys,
                needs_auth,
                num_retries + 1,
            )
        except MazdaTokenExpiredException:
            self.logger.info(
                "Server reports access token was expired (600002). "
                "Resetting cached token — will re-fetch on retry."
            )
            self.access_token = None
            return await self.__api_request_retry(
                method,
                uri,
                query_dict,
                body_dict,
                needs_keys,
                needs_auth,
                num_retries + 1,
            )
        except MazdaSessionExpiredException as ex:
            self.logger.warning(
                "Server reports session conflict (600100). Clearing session ID and re-attaching. Details: %s", ex
            )
            self.device_session_id = None
            if self.session_refresh_provider:
                try:
                    await self.session_refresh_provider()
                except Exception as attach_ex:
                    self.logger.warning("Re-attach after 600100 failed: %s", attach_ex)
            return await self.__api_request_retry(
                method,
                uri,
                query_dict,
                body_dict,
                needs_keys,
                needs_auth,
                num_retries + 1,
            )
        except MazdaRequestInProgressException:
            self.logger.info(
                "Request failed because another request was already in progress. Waiting 30 seconds and trying again."
            )
            await asyncio.sleep(30)
            return await self.__api_request_retry(
                method,
                uri,
                query_dict,
                body_dict,
                needs_keys,
                needs_auth,
                num_retries + 1,
            )

    async def __send_api_request(
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
    ):
        timestamp = self.__get_timestamp_str_ms()
        self.logger.debug("Request details - URI: %s, method: %s, timestamp: %s", uri, method, timestamp)

        original_query_str = ""
        encrypted_query_dict = {}

        if query_dict:
            original_query_str = urlencode(query_dict)
            encrypted_query_dict["params"] = self.__encrypt_payload_using_key(
                original_query_str
            )

        original_body_str = ""
        encrypted_body_str = ""
        if body_dict:
            original_body_str = json.dumps(body_dict)
            encrypted_body_str = self.__encrypt_payload_using_key(original_body_str)

        headers = {
            "device-id": self.base_api_device_id,
            "app-code": self.app_code,
            "app-os": APP_OS,
            "user-agent": USER_AGENT_BASE_API,
            "app-version": APP_VERSION,
            "app-unique-id": APP_PACKAGE_ID,
            "X-acf-sensor-data": self.sensor_data_builder.generate_sensor_data(),
            "req-id": str(uuid.uuid4()).upper(),
            "timestamp": timestamp,
            "region": self.region_header,
            "locale": "en-US",
            "language": "en",
            "Accept": "*/*",
        }

        if needs_auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
            headers["access-token"] = self.access_token

        if self.device_session_id:
            headers["X-device-session-id"] = self.device_session_id

        if "checkVersion" in uri:
            headers["sign"] = self.__get_sign_from_timestamp(timestamp, self.app_code)
            self.logger.debug("checkVersion sign: %s (timestamp: %s, device-id: %s, app_code: %s)", headers["sign"], timestamp, self.base_api_device_id, self.app_code)
        elif method == "GET":
            headers["sign"] = self.__get_sign_from_payload_and_timestamp(
                original_query_str, timestamp
            )
        elif method == "POST":
            headers["sign"] = self.__get_sign_from_payload_and_timestamp(
                original_body_str, timestamp
            )

        response = await self._session.request(
            method,
            self.base_url + uri,
            headers=headers,
            data=encrypted_body_str,
            ssl=ssl_context,
        )

        response_json = await response.json()
        self.logger.debug("Response status: %s, body: %s", response.status, response_json)

        if response_json.get("state") == "S":
            if "checkVersion" in uri:
                return self.__decrypt_payload_using_app_code(response_json["payload"], self.app_code)
            else:
                decrypted_payload = self.__decrypt_payload_using_key(
                    response_json["payload"]
                )
                self.logger.debug("Response payload: %s", decrypted_payload)
                return decrypted_payload
        elif response_json.get("errorCode") == 600001:
            raise MazdaAPIEncryptionException("Server rejected encrypted request")
        elif response_json.get("errorCode") == 600002:
            raise MazdaTokenExpiredException("Token expired")
        elif response_json.get("errorCode") == 600100:
            raise MazdaSessionExpiredException(
                "Session conflict (600100): " + response_json.get("error", "multiple devices detected")
            )
        elif (
            response_json.get("errorCode") == 920000
            and response_json.get("extraCode") == "400S01"
        ):
            raise MazdaRequestInProgressException(
                "Request already in progress, please wait and try again"
            )
        elif (
            response_json.get("errorCode") == 920000
            and response_json.get("extraCode") == "400S11"
        ):
            raise MazdaException(
                "The engine can only be remotely started 2 consecutive times. Please drive the vehicle to reset the counter."
            )
        elif "error" in response_json:
            raise MazdaException("Request failed: " + response_json["error"])
        else:
            raise MazdaException("Request failed for an unknown reason")

    async def __ensure_keys_present(self):
        if self.enc_key is None or self.sign_key is None:
            await self.__retrieve_keys()

    async def __ensure_token_is_valid(self):
        if self.access_token is None:
            self.logger.info("No access token present. Fetching from provider.")
            self.access_token = await self.access_token_provider()

    async def __retrieve_keys(self):
        self.logger.info("Retrieving encryption keys from %s", self.base_url)
        response = await self.__api_request_to_url(
            "POST", self.base_url + "service/checkVersion"
        )
        self.logger.info("Successfully retrieved encryption keys")

        self.enc_key = response["encKey"]
        self.sign_key = response["signKey"]

    async def __api_request_to_url(self, method, full_url, body_dict={}):
        """Send a request to an explicit URL (used for checkVersion on old API)."""
        timestamp = self.__get_timestamp_str_ms()
        headers = {
            "device-id": self.base_api_device_id,
            "app-code": self.app_code,
            "app-os": APP_OS,
            "user-agent": USER_AGENT_BASE_API,
            "app-version": APP_VERSION,
            "app-unique-id": APP_PACKAGE_ID,
            "X-acf-sensor-data": self.sensor_data_builder.generate_sensor_data(),
            "req-id": str(uuid.uuid4()).upper(),
            "timestamp": timestamp,
            "region": self.region_header,
            "locale": "en-US",
            "language": "en",
            "Accept": "*/*",
            "Content-Type": "text/plain",
            "sign": self.__get_sign_from_timestamp(timestamp, self.app_code),
        }
        self.logger.debug("checkVersion to %s, app_code=%s, sign=%s", full_url, self.app_code, headers["sign"])
        response = await self._session.request(method, full_url, headers=headers, data="", ssl=ssl_context)
        response_json = await response.json()
        self.logger.debug("checkVersion response: %s", response_json)
        if response_json.get("state") == "S":
            return self.__decrypt_payload_using_app_code(response_json["payload"], self.app_code)
        elif response_json.get("errorCode") == 600001:
            raise MazdaException("checkVersion rejected (wrong SIGNATURE_MD5). response: " + str(response_json))
        else:
            raise MazdaException("checkVersion failed: " + str(response_json))

    async def close(self):  # noqa: D102
        await self._session.close()
