"""
region_names.py — central place for user‑friendly Mazda region names.

Use in your config_flow (or anywhere you collect the region) like:
    from .region_names import REGION_LABELS, REGION_CHOICES, normalize_region

    # e.g. voluptuous schema example:
    # vol.Required(CONF_REGION, default="MME"): vol.In(REGION_CHOICES)

REGION_CHOICES maps *labels* -> *codes*, so users see "Europa" but you keep "MME".
normalize_region() accepts labels, aliases or codes and returns the canonical code.
"""

# Canonical Mazda region codes -> human labels
REGION_LABELS: dict[str, str] = {
    "MME": "Europa",
    "MNAO": "Nordamerika",
    "MJO": "Japan",
}

# What users will see in a dropdown (label) mapped to the code you store
REGION_CHOICES: dict[str, str] = {
    "Europa": "MME",
    "Nordamerika": "MNAO",
    "Japan": "MJO",
}

# Common aliases you might receive (case-insensitive) -> code
_ALIASES_TO_CODE: dict[str, str] = {
    # Europe
    "europe": "MME",
    "eu": "MME",
    "europa": "MME",
    "mme": "MME",
    # North America
    "north america": "MNAO",
    "north_america": "MNAO",
    "na": "MNAO",
    "us": "MNAO",
    "usa": "MNAO",
    "nordamerika": "MNAO",
    "mnao": "MNAO",
    # Japan
    "japan": "MJO",
    "jp": "MJO",
    "mjo": "MJO",
}


def normalize_region(value: str) -> str:
    """
    Convert a user input (label/alias/code) to a canonical Mazda region code.
    Defaults to "MME" (Europa) if unknown.
    """
    if not value:
        return "MME"
    v_upper = value.upper().strip()
    if v_upper in REGION_LABELS:
        return v_upper
    v_norm = value.strip().lower().replace("-", " ")
    return _ALIASES_TO_CODE.get(v_norm, "MME")
