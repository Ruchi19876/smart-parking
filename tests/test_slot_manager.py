"""
Unit tests for core/slot_manager.py — VEHICLE_TO_ZONE mapping.
Run with:  pytest tests/test_slot_manager.py -v
Only checks the static mapping table (no DB needed).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.slot_manager import VEHICLE_TO_ZONE


def test_every_vehicle_type_has_a_zone():
    expected_types = {"bike", "scooty", "car", "auto", "ev", "heavy"}
    assert expected_types.issubset(VEHICLE_TO_ZONE.keys())


def test_two_wheelers_map_to_zone_a():
    assert VEHICLE_TO_ZONE["bike"] == "A"
    assert VEHICLE_TO_ZONE["scooty"] == "A"


def test_ev_has_dedicated_zone():
    # EVs should not share a zone with regular petrol/diesel four-wheelers
    assert VEHICLE_TO_ZONE["ev"] != VEHICLE_TO_ZONE["car"]


def test_heavy_vehicle_has_dedicated_zone():
    assert VEHICLE_TO_ZONE["heavy"] not in (VEHICLE_TO_ZONE["bike"], VEHICLE_TO_ZONE["car"])
