import asyncio  # noqa: D100
import base64
import hashlib
import json
import logging
import ssl
import time
from urllib.parse import urlencode

import aiohttp

from .crypto_utils import (
    decrypt_aes128cbc_buffer_to_str,
    encrypt_aes128cbc_buffer_to_base64_str,
    encrypt_rsaecbpkcs1_padding,
    generate_usher_device_id_from_seed,
    generate_uuid_from_seed,
)
from .exceptions import (
    MazdaAccountLockedException,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaConfigException,
    MazdaException,
    MazdaLoginFailedException,
    MazdaRequestInProgressException,
    MazdaTokenExpiredException,
)
from .sensordata.sensor_data_builder import SensorDataBuilder
from .ssl_context_configurator.ssl_context_configurator import SSLContextConfigurator

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.load_default_certs()
ssl_context.set_ciphers(
    "DEFAULT:!aNULL:!eNULL:!MD5:!3DES:!DES:!RC4:!IDEA:!SEED:!aDSS:!SRP:!PSK"
)

REGION_CONFIG = {
    "MNAO": {
        "app_code": "202007270941270111799",
        "base_url": "https://0cxo7m58.mazda.com/prod/",
        "usher_url": "https://ptznwbh8.mazda.com/appapi/v1/",
    },
    "MME": {
        "app_code": "202008100250281064816",
        "base_url": "https://e9stj7g7.mazda.com/prod/",
        "usher_url": "https://rz97suam.mazda.com/appapi/v1/",
    },
    "MJO": {
        "app_code": "202009170613074283422",
        "base_url": "https://wcs9p6wj.mazda.com/prod/",
        "usher_url": "https://c5ulfwxr.mazda.com/appapi/v1/",
    },
}

IV = "0102030405060708"
SIGNATURE_MD5 = "C383D8C4D279B78130AD52DC71D95CAA"
APP_PACKAGE_ID = "com.interrait.mymazda"
USER_AGENT_BASE_API = "MyMazda-Android/8.5.2"
USER_AGENT_USHER_API = "MyMazda/8.5.2 (Google Pixel 3a; Android 11)"
APP_OS = "Android"
APP_VERSION = "8.5.2"
USHER_SDK_VERSION = "11.3.0700.001"

MAX_RETRIES = 4
BASE_TIMEOUT = 60  # Increased from 30 to allow more time for API responses
KEEP_ALIVE_TIMEOUT = 300  # Increased from 120 for more stable connections
KEEP_ALIVE_PING_INTERVAL = 30  # Increased from 15 to reduce connection overhead
RATE_LIMIT_WINDOW = 60  # seconds
MAX_REQUESTS_PER_WINDOW = 100
MAX_RETRIES = 5  # Increased from 4 for better error recovery

class Connection:
    """Main class for handling MyMazda API connection."""

    def __init__(self, email, password, region, websession=None):  # noqa: D107
        self._request_timestamps = []
        self.email = email
        self.password = password

        if region in REGION_CONFIG:
            region_config = REGION_CONFIG[region]
            self.app_code = region_config["app_code"]
            self.base_url = region_config["base_url"]
            self.usher_url = region_config["usher_url"]
        else:
            raise MazdaConfigException("Invalid region")

        self.base_api_device_id = generate_uuid_from_seed(email)
        self.usher_api_device_id = generate_usher_device_id_from_seed(email)

        self.enc_key = None
        self.sign_key = None

        self.access_token = None
        self.access_token_expiration_ts = None

        self.sensor_data_builder = SensorDataBuilder()

        if websession is None:
            self._session = aiohttp.ClientSession()
        else:
            self._session = websession
            
        # Initialize connection pool metrics
        self._connection_pool = {
            'total_connections': 0,
            'active_connections': 0,
            'idle_connections': 0,
            'connection_errors': 0
        }

        self.logger = logging.getLogger(__name__)

    def __get_timestamp_str_ms(self):
        return str(int(round(time.time() * 1000)))

    def __get_timestamp_str(self):
        return str(int(round(time.time())))

    def __get_decryption_key_from_app_code(self):
        val1 = (
            hashlib.md5((self.app_code + APP_PACKAGE_ID).encode()).hexdigest().upper()
        )
        val2 = hashlib.md5((val1 + SIGNATURE_MD5).encode()).hexdigest().lower()
        return val2[4:20]

    def __get_temporary_sign_key_from_app_code(self):
        val1 = (
            hashlib.md5((self.app_code + APP_PACKAGE_ID).encode()).hexdigest().upper()
        )
        val2 = hashlib.md5((val1 + SIGNATURE_MD5).encode()).hexdigest().lower()
        return val2[20:32] + val2[0:10] + val2[4:6]

    def __get_sign_from_timestamp(self, timestamp):
        if timestamp is None or timestamp == "":
            return ""

        timestamp_extended = (timestamp + timestamp[6:] + timestamp[3:]).upper()

        temporary_sign_key = self.__get_temporary_sign_key_from_app_code()

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

    def __decrypt_payload_using_app_code(self, payload):
        buf = base64.b64decode(payload)
        key = self.__get_decryption_key_from_app_code()
        decrypted = decrypt_aes128cbc_buffer_to_str(buf, key, IV)
        return json.loads(decrypted)

    def __decrypt_payload_using_key(self, payload):
        if self.enc_key is None or self.enc_key == "":
            raise MazdaException("Missing encryption key")

        buf = base64.b64decode(payload)
        decrypted = decrypt_aes128cbc_buffer_to_str(buf, self.enc_key, IV)
        return json.loads(decrypted)

    def __encrypt_payload_with_public_key(self, password, public_key):
        timestamp = self.__get_timestamp_str()
        encryptedBuffer = encrypt_rsaecbpkcs1_padding(
            password + ":" + timestamp, public_key
        )
        return base64.b64encode(encryptedBuffer).decode("utf-8")

    async def api_request(
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
    ):
        """Make an API request with detailed error handling and logging."""
        self.logger.debug(f"Starting API request to {uri}")
        try:
            # Detailed request tracking
            request_id = f"req_{self.__get_timestamp_str_ms()}"
            self.logger.debug(f"Request ID: {request_id}")
            
            # Validate input parameters
            if not isinstance(query_dict, dict):
                raise MazdaConfigException("query_dict must be a dictionary")
            if not isinstance(body_dict, dict):
                raise MazdaConfigException("body_dict must be a dictionary")
                
            return await self.__api_request_retry(
                method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries=0
            )
        except MazdaException as ex:
            self.logger.error(f"API request failed: {str(ex)}")
            raise
        except Exception as ex:
            self.logger.error(f"Unexpected error during API request: {str(ex)}")
            raise MazdaException(f"Unexpected error: {str(ex)}") from ex

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
        """Handle API request retries with detailed error tracking."""
        if num_retries > MAX_RETRIES:
            error_msg = f"Request to {uri} failed after {MAX_RETRIES} retries"
            self.logger.error(error_msg)
            raise MazdaException(error_msg)

        # Enhanced rate limiting tracking
        now = time.time()
        self._request_timestamps = [t for t in self._request_timestamps if t > now - RATE_LIMIT_WINDOW]
        
        # Calculate rate limit metrics
        requests_in_window = len(self._request_timestamps)
        rate_limit_percentage = (requests_in_window / MAX_REQUESTS_PER_WINDOW) * 100
        
        if requests_in_window >= MAX_REQUESTS_PER_WINDOW:
            wait_time = RATE_LIMIT_WINDOW - (now - self._request_timestamps[0])
            self.logger.warning(
                f"Rate limit reached ({requests_in_window}/{MAX_REQUESTS_PER_WINDOW} requests in last {RATE_LIMIT_WINDOW}s, {rate_limit_percentage:.1f}%). "
                f"Waiting {wait_time:.1f} seconds before retry."
            )
            await asyncio.sleep(wait_time)
        elif rate_limit_percentage > 80:
            self.logger.info(
                f"Approaching rate limit ({requests_in_window}/{MAX_REQUESTS_PER_WINDOW} requests in last {RATE_LIMIT_WINDOW}s, {rate_limit_percentage:.1f}%)"
            )

        # Validate keys and authentication
        try:
            if needs_keys:
                self.logger.debug("Validating encryption keys")
                await self.__ensure_keys_present()
            if needs_auth:
                self.logger.debug("Validating access token")
                await self.__ensure_token_is_valid()
        except MazdaException as ex:
            self.logger.error(f"Pre-request validation failed: {str(ex)}")
            raise

        # Detailed request logging
        retry_message = f" (attempt {num_retries + 1}/{MAX_RETRIES})" if num_retries > 0 else ""
        self.logger.debug(
            f"Sending {method} request to {uri}{retry_message}\n"
            f"Query params: {query_dict}\n"
            f"Body: {body_dict}"
        )
        
        # Track request timing
        request_start = time.time()
        self._request_timestamps.append(request_start)
        self.logger.debug(f"Request started at {request_start}")

        try:
            response = await self.__send_api_request(
                method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries
            )
            request_duration = time.time() - request_start
            self.logger.debug(f"Request completed in {request_duration:.2f} seconds")
            return response
            
        except MazdaAPIEncryptionException as ex:
            self.logger.error(
                "Encryption error: Server rejected encrypted request. Details: "
                f"URI: {uri}, Error: {str(ex)}"
            )
            self.logger.info("Attempting to retrieve new encryption keys")
            await self.__retrieve_keys()
            return await self.__api_request_retry(
                method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries + 1
            )
            
        except MazdaTokenExpiredException as ex:
            self.logger.error(
                "Token expired: Server rejected request due to expired token. Details: "
                f"URI: {uri}, Error: {str(ex)}"
            )
            self.logger.info("Attempting to refresh access token")
            await self.login()
            return await self.__api_request_retry(
                method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries + 1
            )
            
        except MazdaLoginFailedException as ex:
            self.logger.error(
                "Login failed: Authentication unsuccessful. Details: "
                f"URI: {uri}, Error: {str(ex)}"
            )
            self.logger.info("Attempting to re-authenticate")
            await self.login()
            return await self.__api_request_retry(
                method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries + 1
            )
            
        except MazdaRequestInProgressException as ex:
            self.logger.error(
                "Request conflict: Another request is already in progress. Details: "
                f"URI: {uri}, Error: {str(ex)}"
            )
            self.logger.info("Waiting 30 seconds before retry")
            await asyncio.sleep(30)
            return await self.__api_request_retry(
                method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries + 1
            )
            
        except Exception as ex:
            self.logger.error(
                "Unexpected error during API request. Details: "
                f"URI: {uri}, Method: {method}, Error: {str(ex)}"
            )
            raise MazdaException(f"Unexpected error: {str(ex)}") from ex

    async def __send_api_request(
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
        num_retries=0,
    ):
        """Send an API request with enhanced retry and timeout handling."""
        import random
        
        # Enhanced exponential backoff with jitter
        base_delay = min(2 ** num_retries, 60)  # Cap at 60 seconds
        jitter = random.uniform(0, base_delay * 0.1)  # Add up to 10% jitter
        delay = base_delay + jitter
        
        if num_retries > MAX_RETRIES:
            raise MazdaException(f"Max retries ({MAX_RETRIES}) exceeded")
            
        if delay > 0:
            self.logger.debug(f"Waiting {delay:.2f} seconds before retry")
            await asyncio.sleep(delay)
            
        # Enhanced timeout handling with progressive increase
        timeout = aiohttp.ClientTimeout(
            total=BASE_TIMEOUT * (num_retries + 1),  # Increase timeout with retries
            connect=10,
            sock_connect=10,
            sock_read=30
        )
        
        # Connection health check and pooling
        if not self._session or self._session.closed:
            self.logger.warning("Session closed, creating new session with connection pooling")
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(
                    keepalive_timeout=KEEP_ALIVE_TIMEOUT,
                    limit=10,  # Max connections
                    limit_per_host=5,  # Max connections per host
                    enable_cleanup_closed=True  # Clean up closed connections
                )
            )
            
        # Server health check
        try:
            # Ping server with a lightweight request
            ping_response = await self._session.head(
                self.base_url,
                timeout=aiohttp.ClientTimeout(total=5),
                ssl=ssl_context
            )
            if ping_response.status != 200:
                self.logger.warning(f"Server health check failed with status {ping_response.status}")
                raise MazdaException("Server unavailable")
        except Exception as ping_error:
            self.logger.warning(f"Server health check failed: {str(ping_error)}")
            if num_retries < MAX_RETRIES:
                return await self.__send_api_request(
                    method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries + 1
                )
            raise MazdaException("Server unavailable after multiple retries") from ping_error
        
        timestamp = self.__get_timestamp_str_ms()

        original_query_str = ""
        encrypted_query_dict = {}

        if query_dict:
            original_query_str = urlencode(query_dict)
            encrypted_query_dict["params"] = self.__encrypt_payload_using_key(
                original_query_str
            )

        original_body_str = ""
        encrypted_body_Str = ""
        if body_dict:
            original_body_str = json.dumps(body_dict)
            encrypted_body_Str = self.__encrypt_payload_using_key(original_body_str)

        headers = {
            "device-id": self.base_api_device_id,
            "app-code": self.app_code,
            "app-os": APP_OS,
            "user-agent": USER_AGENT_BASE_API,
            "app-version": APP_VERSION,
            "app-unique-id": APP_PACKAGE_ID,
            "access-token": (self.access_token if needs_auth else ""),
            "X-acf-sensor-data": self.sensor_data_builder.generate_sensor_data(),
            "req-id": "req_" + timestamp,
            "timestamp": timestamp,
            "language": "en",
            "region": "us",
            "locale": "en-US",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9"
        }

        if "checkVersion" in uri:
            headers["sign"] = self.__get_sign_from_timestamp(timestamp)
        elif method == "GET":
            headers["sign"] = self.__get_sign_from_payload_and_timestamp(
                original_query_str, timestamp
            )
        elif method == "POST":
            headers["sign"] = self.__get_sign_from_payload_and_timestamp(
                original_body_str, timestamp
            )

        # Enhanced session handling with keep-alive
        try:
            response = await self._session.request(
                method,
                self.base_url + uri,
                headers=headers,
                data=encrypted_body_Str,
                ssl=ssl_context,
                timeout=timeout
            )
            
            # Validate response status
            if response.status >= 500:
                raise MazdaException(f"Server error: {response.status}")
            if response.status == 429:
                retry_after = int(response.headers.get('Retry-After', delay))
                raise MazdaException(f"Rate limited - retry after {retry_after} seconds")
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            self.logger.warning(f"Connection error: {str(ex)}")
            if num_retries < MAX_RETRIES:
                return await self.__send_api_request(
                    method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries + 1
                )
            raise MazdaException(f"Connection failed after {MAX_RETRIES} retries") from ex

        response_json = await response.json()

        if response_json.get("state") == "S":
            if "checkVersion" in uri:
                return self.__decrypt_payload_using_app_code(response_json["payload"])
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
        if self.access_token is None or self.access_token_expiration_ts is None:
            self.logger.info("No access token present. Logging in.")
        elif self.access_token_expiration_ts <= time.time():
            self.logger.info("Access token is expired. Fetching a new one.")
            self.access_token = None
            self.access_token_expiration_ts = None

        if (
            self.access_token is None
            or self.access_token_expiration_ts is None
            or self.access_token_expiration_ts <= time.time()
        ):
            await self.login()

    async def __retrieve_keys(self):
        self.logger.info("Retrieving encryption keys")
        response = await self.api_request(
            "POST", "service/checkVersion", needs_keys=False, needs_auth=False
        )
        self.logger.info("Successfully retrieved encryption keys")

        self.enc_key = response["encKey"]
        self.sign_key = response["signKey"]

    async def login(self):  # noqa: D102
        self.logger.info("Logging in as " + self.email)  # noqa: G003
        self.logger.info("Retrieving public key to encrypt password")
        encryption_key_response = await self._session.request(
            "GET",
            self.usher_url + "system/encryptionKey",
            params={
                "appId": "MazdaApp",
                "locale": "en-US",
                "deviceId": self.usher_api_device_id,
                "sdkVersion": USHER_SDK_VERSION,
            },
            headers={"User-Agent": USER_AGENT_USHER_API},
            ssl=ssl_context,
        )

        encryption_key_response_json = await encryption_key_response.json()

        public_key = encryption_key_response_json["data"]["publicKey"]
        encrypted_password = self.__encrypt_payload_with_public_key(
            self.password, public_key
        )
        version_prefix = encryption_key_response_json["data"]["versionPrefix"]

        self.logger.info("Sending login request")
        login_response = await self._session.request(
            "POST",
            self.usher_url + "user/login",
            headers={"User-Agent": USER_AGENT_USHER_API},
            json={
                "appId": "MazdaApp",
                "deviceId": self.usher_api_device_id,
                "locale": "en-US",
                "password": version_prefix + encrypted_password,
                "sdkVersion": USHER_SDK_VERSION,
                "userId": self.email,
                "userIdType": "email",
            },
            ssl=ssl_context,
        )

        login_response_json = await login_response.json()

        if login_response_json.get("status") == "INVALID_CREDENTIAL":
            self.logger.error("Login failed due to invalid email or password")
            raise MazdaAuthenticationException("Invalid email or password")
        if login_response_json.get("status") == "USER_LOCKED":
            self.logger.error("Login failed to account being locked")
            raise MazdaAccountLockedException("Account is locked")
        if login_response_json.get("status") != "OK":
            self.logger.error(
                "Login failed"  # noqa: G003
                + (
                    (": " + login_response_json.get("status", ""))
                    if ("status" in login_response_json)
                    else ""
                )
            )
            raise MazdaLoginFailedException("Login failed")

        self.logger.info("Successfully logged in as " + self.email)  # noqa: G003
        self.access_token = login_response_json["data"]["accessToken"]
        self.access_token_expiration_ts = login_response_json["data"][
            "accessTokenExpirationTs"
        ]

    async def close(self):  # noqa: D102
        await self._session.close()
