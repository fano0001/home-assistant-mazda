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
#MOBILE_REDIRECT_URI = "msauth.com.mazdausa.mazdaiphone://auth" #iOS Value
MOBILE_REDIRECT_URI = "msauth://com.interrait.mymazda/%2FnKMu1%2BlCjy5%2Be7OF9vfp4eFBks%3D"

# Regional OAuth2 hosts
OAUTH2_HOSTS = {
    "MNAO": "na.id.mazda.com",
    "MME": "eu.id.mazda.com",
    "MJO": "jp.id.mazda.com",  # TBD - needs verification
}

# MSAL client identifiers (sent with authorize requests)
# Values confirmed from com.interrait.mymazda 9.0.8 APK (msal/BuildConfig.java, AuthenticationConstants.java)
#MSAL_CLIENT_SKU = "MSAL.iOS"   # old iOS value
#MSAL_CLIENT_VER = "1.6.3"      # old iOS MSAL version
MSAL_CLIENT_SKU = "MSAL.Android"
MSAL_CLIENT_VER = "5.4.0"
MSAL_APP_NAME = "MyMazda"
MSAL_APP_VER = "9.0.8"
