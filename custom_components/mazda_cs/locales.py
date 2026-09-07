"""Locale resolution for Mazda Connected Services.

Azure AD B2C's sign-in journey consumes locale and country as input claims on the
authorize request. The MyMazda app derives them from the country/language pair the
user picks on first launch, which it resolves against a table bundled in the APK
(``assets/appdata/getCountryAndLocale.json``). Two distinct values come out of that
table and they are *not* interchangeable:

``locale``
    Mechanically ``<language>-<SELECTED COUNTRY>`` (``en-DE`` for an English-speaking
    user in Germany). Source of the ``country`` authorize param and of the ``locale``
    and ``language`` API headers.

``isoLocale``
    The canonical content tag for that language in that market — ``en-IE`` in most of
    Europe but ``en-GB`` in the UK, ``de-DE``/``de-CH``/``de-AT`` for German. Sent as
    ``ui_locales``.

Home Assistant has no country/language picker of its own for this integration, so we
derive both from ``hass.config`` and fall back to the region default in
``REGION_CONFIG`` whenever that does not yield a combination Mazda actually offers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .pymazda.connection import REGION_CONFIG

# MME markets, from assets/appdata/getCountryAndLocale.json (MyMazda 9.5.0).
MME_COUNTRIES = frozenset(
    {
        "AD", "AL", "AT", "BA", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE",
        "ES", "FI", "FO", "FR", "GB", "GR", "HR", "HU", "IE", "IS", "IT", "LI",
        "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL", "PT",
        "RO", "RS", "SE", "SI", "SK", "SM", "XK",
    }
)  # fmt: skip

# Language subtag -> isoLocale used in most MME markets.
MME_ISO_LOCALES = {
    "bg": "bg-BG",
    "cs": "cs-CZ",
    "da": "da-DK",
    "de": "de-DE",
    "el": "el-GR",
    "en": "en-IE",
    "es": "es-ES",
    "et": "et-EE",
    "fi": "fi-FI",
    "fr": "fr-FR",
    "hr": "hr-HR",
    "hu": "hu-HU",
    "it": "it-IT",
    "lt": "lt-LT",
    "lv": "lv-LV",
    "nb": "nb-NO",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "pt": "pt-PT",
    "ro": "ro-RO",
    "sk": "sk-SK",
    "sl": "sl-SI",
    "sr": "sr-RS",
    "sv": "sv-SE",
}

# The markets Mazda serves German through its "DM" distributor take de-CH, not de-DE.
_DE_CH_MARKETS = (
    "AL", "BA", "BG", "CH", "CY", "FO", "GR", "LI", "MD", "ME", "MK", "MT", "RS", "XK",
)  # fmt: skip

# (language, country) pairs where the market overrides the canonical isoLocale.
MME_ISO_OVERRIDES = {
    **{("de", country): "de-CH" for country in _DE_CH_MARKETS},
    ("de", "AT"): "de-AT",
    ("en", "GB"): "en-GB",
    ("fr", "BE"): "fr-BE",
    ("fr", "LU"): "fr-BE",
    ("fr", "CH"): "fr-CH",
    ("it", "CH"): "it-CH",
    ("nl", "BE"): "nl-BE",
    ("sr", "ME"): "sr-ME",
}

# ui_locales only — B2C wants the script-qualified Serbian forms (AuthParams.b()).
UI_LOCALE_ALIASES = {"sr-RS": "sr-Latn-RS", "sr-ME": "sr-Latn-ME"}


@dataclass(frozen=True)
class ResolvedLocale:
    """The locale values one config entry sends to Mazda."""

    locale: str
    """``<language>-<COUNTRY>`` — API ``locale`` header, and source of ``country``."""

    ui_locale: str
    """Canonical market tag for ``ui_locales``, Serbian script-qualified."""

    @property
    def country(self) -> str:
        """ISO country — ``country`` and ``default_international_phone_code``."""
        return self.locale.split("-")[1]

    @property
    def language(self) -> str:
        """Language subtag — Conductor ``language`` (ConductorConfig.t() in the APK
        derives it the same way, from the first subtag of ``locale``)."""
        return self.locale.split("-")[0]


def _language_subtag(ha_language: str | None) -> str | None:
    """Return the first subtag of an HA language code ("pt-BR" -> "pt")."""
    return ha_language.split("-")[0].lower() if ha_language else None


def resolve_locale(
    region: str,
    ha_language: str | None = None,
    ha_country: str | None = None,
) -> ResolvedLocale:
    """Resolve the locale for a region, falling back to the region default."""
    default = REGION_CONFIG[region]["locale"]
    language = _language_subtag(ha_language)

    if region == "MME":
        if language not in MME_ISO_LOCALES:
            language = default.split("-")[0]
        country = (ha_country or "").upper()
        if country not in MME_COUNTRIES:
            # No usable country: fall back to the canonical market for the language
            # (it -> IT, fr -> FR) rather than defaulting to IE.
            country = MME_ISO_LOCALES[language].split("-")[1]
        locale = f"{language}-{country}"
        iso_locale = MME_ISO_OVERRIDES.get(
            (language, country), MME_ISO_LOCALES[language]
        )
    elif region == "MCI" and language == "fr":
        # Canada's only departure from the en-CA default; locale == isoLocale there.
        locale = iso_locale = "fr-CA"
    else:
        # MNAO / MJO / MA each offer a single country with a single language.
        locale = iso_locale = default

    return ResolvedLocale(locale, UI_LOCALE_ALIASES.get(iso_locale, iso_locale))
