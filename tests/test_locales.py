"""Tests for ``locales.resolve_locale``.

Azure AD B2C's sign-in journey feeds ``ui_locales`` and ``country`` into the
``OtpFunc-SendCode`` claims exchange, so a value Mazda does not recognise surfaces as
an opaque ``InternalServerError`` on the verification-code page rather than as a
validation error. The expectations below are transcribed from
``assets/appdata/getCountryAndLocale.json`` in MyMazda 9.5.0: every ``locale`` this
resolver can emit has to be a pair the app itself offers.

Note the two values are distinct in Europe — an English-speaking user in Germany gets
``ui_locales=en-IE`` (the market's canonical English tag) but ``country=DE``.
"""

import pytest

from custom_components.mazda_cs.locales import (
    MME_COUNTRIES,
    MME_ISO_LOCALES,
    MME_ISO_OVERRIDES,
    UI_LOCALE_ALIASES,
    resolve_locale,
)
from custom_components.mazda_cs.pymazda.connection import REGION_CONFIG

# (region, hass.config.language, hass.config.country, ui_locales, country, locale)
RESOLUTIONS = [
    # Single-country regions: no user input can move them off the default.
    ("MNAO", "en", "US", "en-US", "US", "en-US"),
    ("MNAO", "de", "DE", "en-US", "US", "en-US"),
    ("MJO", "ja", "JP", "ja-JP", "JP", "ja-JP"),
    ("MA", "en", "AU", "en-AU", "AU", "en-AU"),
    # Canada: French is the only departure from the en-CA default.
    ("MCI", "fr", "CA", "fr-CA", "CA", "fr-CA"),
    ("MCI", "fr-CA", "CA", "fr-CA", "CA", "fr-CA"),
    ("MCI", "en", "CA", "en-CA", "CA", "en-CA"),
    ("MCI", "de", "CA", "en-CA", "CA", "en-CA"),
    # Europe: ui_locales is the market's canonical tag, country is where you are.
    ("MME", "de", "DE", "de-DE", "DE", "de-DE"),
    ("MME", "en", "DE", "en-IE", "DE", "en-DE"),
    ("MME", "nl", "NL", "nl-NL", "NL", "nl-NL"),
    ("MME", "en", "GB", "en-GB", "GB", "en-GB"),
    ("MME", "de", "GB", "de-DE", "GB", "de-GB"),
    # ...including the market overrides.
    ("MME", "de", "CH", "de-CH", "CH", "de-CH"),
    ("MME", "de", "AT", "de-AT", "AT", "de-AT"),
    ("MME", "de", "RS", "de-CH", "RS", "de-RS"),
    ("MME", "fr", "BE", "fr-BE", "BE", "fr-BE"),
    ("MME", "fr", "LU", "fr-BE", "LU", "fr-LU"),
    ("MME", "fr", "CH", "fr-CH", "CH", "fr-CH"),
    ("MME", "fr", "FR", "fr-FR", "FR", "fr-FR"),
    ("MME", "it", "CH", "it-CH", "CH", "it-CH"),
    ("MME", "nl", "BE", "nl-BE", "BE", "nl-BE"),
    # A language HA carries a region or script on still resolves by its subtag.
    ("MME", "pt-BR", "PT", "pt-PT", "PT", "pt-PT"),
    ("MME", "sr-Latn", "RS", "sr-Latn-RS", "RS", "sr-RS"),
    ("MME", "sr", "ME", "sr-Latn-ME", "ME", "sr-ME"),
    ("MME", "DE", "de", "de-DE", "DE", "de-DE"),
]


@pytest.mark.parametrize(
    ("region", "language", "country", "ui_locale", "expected_country", "locale"),
    RESOLUTIONS,
)
def test_resolve_locale(region, language, country, ui_locale, expected_country, locale):
    """Each (region, language, country) resolves to the tags the app would send."""
    resolved = resolve_locale(region, language, country)

    assert resolved.ui_locale == ui_locale
    assert resolved.country == expected_country
    assert resolved.locale == locale


# (region, hass.config.language, hass.config.country, ui_locales, country)
FALLBACKS = [
    # Nothing configured at all — HA can report either field as None.
    ("MME", None, None, "en-IE", "IE"),
    ("MME", "de", None, "de-DE", "DE"),
    ("MME", None, "DE", "en-IE", "DE"),
    ("MME", "", "", "en-IE", "IE"),
    # An unusable country falls back to the language's canonical market, not to the
    # region default — an Italian with no HA country still gets country=IT.
    ("MME", "it", None, "it-IT", "IT"),
    ("MME", "fr", None, "fr-FR", "FR"),
    ("MME", "nl", None, "nl-NL", "NL"),
    # A country Mazda does not serve from this region, and a language it does not
    # offer, each fall back independently rather than composing a bogus pair.
    ("MME", "de", "US", "de-DE", "DE"),
    ("MME", "ja", "DE", "en-IE", "DE"),
    ("MME", "ja", "US", "en-IE", "IE"),
    ("MCI", None, None, "en-CA", "CA"),
    ("MNAO", None, None, "en-US", "US"),
]


@pytest.mark.parametrize(
    ("region", "language", "country", "ui_locale", "expected_country"), FALLBACKS
)
def test_resolve_locale_falls_back(
    region, language, country, ui_locale, expected_country
):
    """Missing or unsupported input falls back to the region default per field."""
    resolved = resolve_locale(region, language, country)

    assert resolved.ui_locale == ui_locale
    assert resolved.country == expected_country


@pytest.mark.parametrize("region", sorted(REGION_CONFIG))
def test_every_region_resolves_without_hass_config(region):
    """No region may raise when hass.config carries neither language nor country."""
    resolved = resolve_locale(region)

    assert resolved.locale == REGION_CONFIG[region]["locale"]
    assert resolved.ui_locale == REGION_CONFIG[region]["locale"]


def test_mme_overrides_stay_within_the_known_tables():
    """Guard the hand-transcribed MME tables against typos."""
    for language, country in MME_ISO_OVERRIDES:
        assert language in MME_ISO_LOCALES
        assert country in MME_COUNTRIES


def test_mme_covers_every_language_and_market():
    """No MME language/market pair is rejected or resolves outside the known tags."""
    known = set(MME_ISO_LOCALES.values()) | set(MME_ISO_OVERRIDES.values())
    known |= set(UI_LOCALE_ALIASES.values())

    for language in MME_ISO_LOCALES:
        for country in MME_COUNTRIES:
            resolved = resolve_locale("MME", language, country)

            assert resolved.locale == f"{language}-{country}"
            assert resolved.ui_locale in known
