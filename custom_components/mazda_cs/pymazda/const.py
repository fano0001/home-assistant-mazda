"""Constants shared across the integration and pymazda.

A constant belongs here if more than one module uses it, or if it has to be
checked when Mazda updates the app. Key derivation (SIGN_PACKAGE_ID and the
signing certificates), region tables and Firebase project IDs stay in the module
that uses them.

Keep this module free of imports: importing connection.py loads OpenSSL settings.
"""

# MyMazda app: check on every app update (AndroidManifest.xml)
APP_NAME = "MyMazda"
APP_PACKAGE_ID = "com.interrait.mymazda"
APP_VERSION = "10.0.1"  # versionName
APP_VERSION_CODE = "653"  # versionCode
APP_TARGET_SDK = "36"  # targetSdkVersion

# Libraries bundled in the app: check on every app update
MSAL_CLIENT_SKU = "MSAL.Android"  # AuthenticationConstants.java
MSAL_CLIENT_VER = "5.4.0"  # msal/BuildConfig.java
FIS_SDK_VERSION = "a:19.0.1"  # "sdkVersion" in the Firebase Installations request
FCM_CLIENT_LIBRARY = "fcm-25.0.1"  # "cliv" in the Firebase Messaging request

# Android device we present: our choice, since the app reads these from the phone.
# ANDROID_SDK (SDK_INT) and DEVICE_BUILD must belong to ANDROID_VERSION.
ANDROID_VERSION = "16"
ANDROID_SDK = "36"
DEVICE_MODEL = "Pixel 9"
DEVICE_ABI = "arm64-v8a"
DEVICE_BUILD = "BP2A.250605.031.A2"

# Mazda API requests
USER_AGENT_BASE_API = f"{APP_NAME}/{APP_VERSION} (Linux; Android {ANDROID_VERSION})"

# Android's default, sent when an app sets no User-Agent, as MSAL does
USER_AGENT_DALVIK = (
    f"Dalvik/2.1.0 (Linux; U; Android {ANDROID_VERSION}; "
    f"{DEVICE_MODEL} Build/{DEVICE_BUILD})"
)
