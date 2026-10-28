"""Konstanten der Spielzeug Wiegestation."""

from __future__ import annotations

DOMAIN = "spielzeug_wiegestation"

CELL_COUNT = 4  # eine Platte auf vier Wägezellen

# Eintrag (data)
CONF_CELLS = "cells"  # die Rohwert-Sensoren der vier Zellen, in der Reihenfolge Zelle 1 bis 4
CONF_NAME = "name"
FIELD_CELL = "cell_"  # Feldname im Formular: cell_1 bis cell_4

# Optionen
OPT_STABLE_SECONDS = "stable_seconds"
OPT_STABLE_TOLERANCE = "stable_tolerance_g"
OPT_OCCUPIED = "occupied_g"

DEFAULT_STABLE_SECONDS = 2.0
DEFAULT_STABLE_TOLERANCE = 2.0
DEFAULT_OCCUPIED = 5.0
OCCUPIED_RELEASE = 0.6  # „belegt“ geht unter diesem Anteil der Schwelle wieder aus (verhindert Flackern)

# Eichen
MIN_LOAD_COUNTS = 2000  # weniger Änderung der Rohwerte (Summe über alle Zellen) gilt als „nichts aufgelegt“
MAX_FIT_ERROR_PERCENT = 3.0  # größere Abweichung der Eichung gegenüber den aufgelegten Gewichten wird gemeldet

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.calibration"

# Zustände des Sensors „Kalibrierung“
CAL_NONE = "not_calibrated"
CAL_DONE = "calibrated"

MINOR_VERSION = 1
