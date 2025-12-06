from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntityDescription


# Eigene, getypte Erweiterung der HA-Description.
# frozen=True weil HA's SensorEntityDescription frozen ist.
@dataclass(frozen=True, slots=True)
class MazdaSensorDescription(SensorEntityDescription):
    # Ist der Sensor für diesen Status verfügbar?
    available_fn: Callable[[Any], bool] | None = None
    # Wert aus dem Status extrahieren/berechnen
    value_fn: Callable[[Any], Any] | None = None


def _pct(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if v < 0 or v > 100:
            return None
        return float(v)
    except Exception:
        return None


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


# V2-Sensorliste wird später befüllt (follow-up),
# hier nur das getypte Gerüst, damit mypy/ruff grün sind.
SENSORS: list[MazdaSensorDescription] = []
