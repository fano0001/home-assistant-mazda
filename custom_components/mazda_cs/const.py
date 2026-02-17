"""Constants for the Mazda Connected Services integration."""

DOMAIN = "mazda_cs"

DATA_CLIENT = "mazda_client"
DATA_COORDINATOR = "coordinator"
DATA_REGION = "region"
DATA_VEHICLES = "vehicles"

MAZDA_REGIONS = {"MNAO": "North America", "MME": "Europe", "MJO": "Japan"}

# Azure AD B2C OAuth2 configuration
OAUTH2_TENANT = "47801034-62d1-49f6-831b-ffdcf04f13fc"
OAUTH2_POLICY = "b2c_1a_signin"
OAUTH2_CLIENT_ID = "2daf581c-65c1-4fdb-b46a-efa98c6ba5b7"
OAUTH2_SCOPES = [
    "https://pduspb2c01.onmicrosoft.com/0728deea-be48-4382-9ef1-d4ff6d679ffa/cv",
    "openid",
    "profile",
    "offline_access",
]
MOBILE_REDIRECT_URI = "msauth.com.mazdausa.mazdaiphone://auth"

# Regional OAuth2 hosts
OAUTH2_HOSTS = {
    "MNAO": "na.id.mazda.com",
    "MME": "eu.id.mazda.com",
    "MJO": "jp.id.mazda.com",  # TBD - needs verification
}

# MSAL client identifiers (sent with authorize requests)
MSAL_CLIENT_SKU = "MSAL.iOS"
MSAL_CLIENT_VER = "1.6.3"
MSAL_APP_NAME = "MyMazda"
MSAL_APP_VER = "9.0.8"
