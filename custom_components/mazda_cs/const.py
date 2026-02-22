"""Constants for the Mazda Connected Services integration."""

DOMAIN = "mazda_cs"

DATA_CLIENT = "mazda_client"
DATA_COORDINATOR = "coordinator"
DATA_REGION = "region"
DATA_VEHICLES = "vehicles"

MAZDA_REGIONS = {"MNAO": "North America", "MCI": "Canada", "MME": "Europe", "MJO": "Japan", "MA": "Australia"}

# Per-region Azure AD B2C OAuth2 configuration
# Values sourced from assets/res/raw/*_mzal_config.json in com.interrait.mymazda 9.0.8 APK
OAUTH2_POLICY = "b2c_1a_signin"
OAUTH2_AUTH = {
    "MNAO": {
        "tenant_id": "47801034-62d1-49f6-831b-ffdcf04f13fc",
        "client_id": "2daf581c-65c1-4fdb-b46a-efa98c6ba5b7",
        "scopes": [
            "https://pduspb2c01.onmicrosoft.com/0728deea-be48-4382-9ef1-d4ff6d679ffa/cv",
            "openid",
            "profile",
            "offline_access",
        ],
    },
    "MCI": {  # Canada — shares MNAO B2C tenant
        "tenant_id": "47801034-62d1-49f6-831b-ffdcf04f13fc",
        "client_id": "2daf581c-65c1-4fdb-b46a-efa98c6ba5b7",
        "scopes": [
            "https://pduspb2c01.onmicrosoft.com/0728deea-be48-4382-9ef1-d4ff6d679ffa/cv",
            "openid",
            "profile",
            "offline_access",
        ],
    },
    "MME": {
        "tenant_id": "432b587f-88ad-40aa-9e5d-e6bcf9429e8d",
        "client_id": "cbfe43e1-6949-42fe-996e-1a56f41a891d",
        "scopes": [
            "https://pdeupb2c01.onmicrosoft.com/dcd35c5a-b32f-4add-ac6c-ba6e8bbfa11b/cv",
            "openid",
            "profile",
            "offline_access",
        ],
    },
    "MJO": {
        "tenant_id": "87c951ae-e146-410a-aa89-0376a7f23c1b",
        "client_id": "455191ae-e98e-4748-8bc6-57a5a570f1c2",
        "scopes": [
            "https://pdjppb2c01.onmicrosoft.com/1c6d5f69-fea6-4019-93df-899ae820b0f4/cv",
            "openid",
            "profile",
            "offline_access",
        ],
    },
    "MA": {
        "tenant_id": "86d3f546-313e-4ee7-b2aa-10a60dff17ca",
        "client_id": "b67a5960-6512-4221-a7ff-166e91f8a584",
        "scopes": [
            "https://pdaupb2c01.onmicrosoft.com/9899c693-8a85-4d6d-82a4-edd9ba8308f7/cv",
            "openid",
            "profile",
            "offline_access",
        ],
    },
}

MOBILE_REDIRECT_URI = "msauth://com.interrait.mymazda/%2FnKMu1%2BlCjy5%2Be7OF9vfp4eFBks%3D"

# Regional OAuth2 hosts (authority_host_name from *_mzal_config.json)
OAUTH2_HOSTS = {
    "MNAO": "na.id.mazda.com",
    "MCI":  "na.id.mazda.com",  # Canada shares MNAO auth infrastructure, confirmed in mzal config
    "MME":  "eu.id.mazda.com",
    "MJO":  "ap.id.mazda.com",
    "MA":   "au.id.mazda.com",
}

# MSAL client identifiers (sent with authorize requests)
# Values confirmed from com.interrait.mymazda 9.0.8 APK (msal/BuildConfig.java, AuthenticationConstants.java)
MSAL_CLIENT_SKU = "MSAL.Android"
MSAL_CLIENT_VER = "5.4.0"
MSAL_APP_NAME = "MyMazda"
MSAL_APP_VER = "9.0.8"