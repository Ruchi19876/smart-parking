"""
Unit tests for core/billing_engine.py — calculate_fee()
Run with:  pytest tests/test_billing_engine.py -v
No database or Flask app required; calculate_fee() is a pure function.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.billing_engine import calculate_fee


def test_car_within_first_hour():
    # Car: first hour flat rate = 20
    assert calculate_fee(30, "car") == 20.0
    assert calculate_fee(60, "car") == 20.0


def test_car_second_hour_rounds_up():
    # 61 minutes => 1 extra (rounded-up) hour => 20 + 1*10 = 30
    assert calculate_fee(61, "car") == 30.0


def test_car_multiple_hours():
    # 3 hours flat (180 min) => 20 + 2*10 = 40
    assert calculate_fee(180, "car") == 40.0
    # 3h01m (181 min) rounds up to 4 hours => 20 + 3*10 = 50
    assert calculate_fee(181, "car") == 50.0


def test_bike_pricing():
    # Bike: first hour = 10, per-hour = 5
    assert calculate_fee(45, "bike") == 10.0
    assert calculate_fee(90, "bike") == 15.0   # 10 + 1*5


def test_heavy_vehicle_pricing():
    # Heavy: first hour = 40, per-hour = 20
    assert calculate_fee(60, "heavy") == 40.0
    assert calculate_fee(125, "heavy") == 80.0  # 40 + 2*20 (rounded up to 3 total hrs -> 2 extra)


def test_ev_pricing():
    # EV: first hour = 25, per-hour = 12
    assert calculate_fee(60, "ev") == 25.0
    assert calculate_fee(61, "ev") == 37.0


def test_unknown_vehicle_type_defaults_to_car_rate():
    # Falls back to (20, 10) default when vehicle type not in pricing map
    assert calculate_fee(60, "spaceship") == 20.0


def test_zero_duration():
    # Edge case: 0 minutes still charges the first-hour flat rate
    assert calculate_fee(0, "car") == 20.0
