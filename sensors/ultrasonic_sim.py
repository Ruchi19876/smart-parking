"""
Module 1: Ultrasonic Distance Sensor Simulation (HC-SR04 behavior)
===================================================================
REAL SENSOR EXPLANATION (for viva):
  A real HC-SR04 ultrasonic sensor works by sending out a burst of ultrasonic sound
  at 40kHz and measuring how long the echo takes to bounce back from an object.
  Formula: distance (cm) = (echo_time_in_microseconds × speed_of_sound) / 2
  Speed of sound ≈ 0.0343 cm/µs at room temperature.
  If the echo returns quickly → object is close → slot is OCCUPIED.
  If no echo or very late echo → slot is FREE.
  Threshold: if distance < 10 cm → vehicle detected (OCCUPIED).

  In this simulation, we generate a fake "echo time" mathematically and apply
  the exact same formula a real sensor uses — the physics is real, only the
  hardware pulse is replaced by a Python random value.
"""

import random
import time
import math

# Speed of sound in cm per microsecond (real constant)
SPEED_OF_SOUND_CM_PER_US = 0.0343

# If measured distance is below this threshold (cm), slot is considered OCCUPIED
OCCUPANCY_THRESHOLD_CM = 10.0

# Maximum measurable range of HC-SR04 (real spec: 400 cm)
MAX_RANGE_CM = 400.0


def simulate_echo_time(slot_occupied: bool) -> float:
    """
    Simulate the time (in microseconds) for ultrasonic echo to return.
    
    Real sensor: emits pulse → echo bounces back from car roof → time measured.
    If a car is parked: echo time is short (car is close, ~5-8 cm from sensor).
    If slot is empty: echo time is long (no nearby object, >400 cm away).
    
    We add small random noise to mimic real sensor variance/jitter.
    """
    if slot_occupied:
        # Car is about 5–9 cm below the sensor (mounted on ceiling/post)
        actual_distance_cm = random.uniform(5.0, 9.0)
    else:
        # No car — sensor reads far distance (floor ~300–400 cm away)
        actual_distance_cm = random.uniform(280.0, 400.0)

    # Add small noise (±0.5 cm) to simulate real sensor jitter
    actual_distance_cm += random.uniform(-0.5, 0.5)
    actual_distance_cm = max(2.0, actual_distance_cm)  # minimum physical distance

    # Reverse the formula to get echo time: time = (distance × 2) / speed_of_sound
    echo_time_us = (actual_distance_cm * 2) / SPEED_OF_SOUND_CM_PER_US
    return echo_time_us


def calculate_distance(echo_time_us: float) -> float:
    """
    Convert echo time (microseconds) to distance (cm).
    
    This is the EXACT formula used in real HC-SR04 sensor code:
        distance = (echo_time × speed_of_sound) / 2
    
    Divide by 2 because the sound travels TO the object and BACK (two-way trip).
    """
    distance_cm = (echo_time_us * SPEED_OF_SOUND_CM_PER_US) / 2
    return round(distance_cm, 2)


def read_slot_sensor(slot_id: int, current_state: bool) -> dict:
    """
    Main function: Read a single parking slot's ultrasonic sensor.
    
    Parameters:
        slot_id      : The slot number (e.g. 1, 2, ... 16)
        current_state: True if slot is currently occupied, False if free
    
    Returns a dictionary with full sensor reading details, just like
    a real IoT sensor would publish to an MQTT broker or REST endpoint.
    
    The reading includes: sensor_id, echo_time, distance, is_occupied, timestamp.
    """
    # Simulate the echo time based on whether a car is present
    echo_time = simulate_echo_time(current_state)

    # Calculate distance using the real HC-SR04 formula
    distance = calculate_distance(echo_time)

    # Apply threshold: if distance < 10 cm → vehicle detected
    is_occupied = distance < OCCUPANCY_THRESHOLD_CM

    # Build and return the sensor reading payload
    reading = {
        "sensor_type": "ULTRASONIC_HC_SR04",
        "sensor_id": f"ULTRA_SLOT_{slot_id:02d}",
        "slot_id": slot_id,
        "echo_time_us": round(echo_time, 2),
        "distance_cm": distance,
        "is_occupied": is_occupied,
        "threshold_cm": OCCUPANCY_THRESHOLD_CM,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "raw_reading": f"{distance} cm"
    }

    return reading


def simulate_vehicle_approach(slot_id: int, steps: int = 5) -> list:
    """
    Simulate a vehicle gradually pulling into a slot.
    
    Real behavior: a real sensor sees the distance DECREASE over time
    as the car slowly drives in. This function returns a sequence of readings
    showing the distance dropping from ~200 cm → ~7 cm, just like a real sensor
    would stream to a controller board during parking.
    
    This is used for the animated "vehicle arriving" effect on the dashboard.
    """
    readings = []
    # Start far away, approach to close
    distances = [200, 150, 100, 50, 20, 12, 8, 7]

    for dist in distances:
        # Add noise
        noisy_dist = dist + random.uniform(-2, 2)
        echo_time = (noisy_dist * 2) / SPEED_OF_SOUND_CM_PER_US
        reading = {
            "sensor_type": "ULTRASONIC_HC_SR04",
            "sensor_id": f"ULTRA_SLOT_{slot_id:02d}",
            "slot_id": slot_id,
            "echo_time_us": round(echo_time, 2),
            "distance_cm": round(noisy_dist, 2),
            "is_occupied": noisy_dist < OCCUPANCY_THRESHOLD_CM,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "raw_reading": f"{round(noisy_dist, 2)} cm"
        }
        readings.append(reading)

    return readings
