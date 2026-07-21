"""
Module 1: RFID / ANPR Camera Simulation (License Plate Recognition)
====================================================================
REAL SENSOR EXPLANATION (for viva):
  Two technologies can identify vehicles at a parking gate:

  1. RFID (Radio Frequency Identification):
     - Each registered vehicle has an RFID tag on the windscreen
     - An RFID reader at the gate emits radio waves (typically 13.56 MHz)
     - The passive RFID tag absorbs the signal, powers up, and broadcasts its UID
     - The reader captures the UID and looks it up in the database
     - No battery needed in the tag — powered by the radio wave itself

  2. ANPR (Automatic Number Plate Recognition) Camera:
     - A camera captures the vehicle's front/rear number plate
     - Computer vision (OCR) reads the plate characters from the image
     - The system matches the plate to a registered user in the database
     - Modern systems use YOLO + OCR or dedicated LPR (License Plate Reader) chips

  In this simulation:
     - We skip actual image capture and OCR (no camera hardware)
     - Instead, we generate a REALISTIC Indian vehicle registration plate
       in the correct format: [State Code][District Code][Series][Number]
     - Example: TS09EZ4521 (Telangana, Hyderabad district, EZ series, 4521)
     - This simulates what ANPR would OUTPUT after reading a plate

Indian number plate format: XX DD LL NNNN
  XX = State code (e.g. TS, AP, MH, KA, DL)
  DD = District number (01-99)
  LL = Letter series (AA-ZZ)
  NNNN = 4-digit number (0001-9999)
"""

import random
import time
import string

# Indian state codes with their names (for realism)
STATE_CODES = {
    "TS": "Telangana",
    "AP": "Andhra Pradesh",
    "MH": "Maharashtra",
    "KA": "Karnataka",
    "DL": "Delhi",
    "TN": "Tamil Nadu",
    "KL": "Kerala",
    "GJ": "Gujarat",
    "RJ": "Rajasthan",
    "UP": "Uttar Pradesh"
}

# Common district numbers for demo (Hyderabad = 09, Bangalore = 05, etc.)
DISTRICT_RANGES = {
    "TS": (1, 33),
    "AP": (1, 26),
    "MH": (1, 50),
    "KA": (1, 35),
    "DL": (1, 13),
    "TN": (1, 75),
    "KL": (1, 14),
    "GJ": (1, 35),
    "RJ": (1, 51),
    "UP": (1, 95)
}


def generate_plate_number() -> str:
    """
    Generate a realistic random Indian vehicle registration number.
    
    Format: [StateCode][DistrictNum][LetterSeries][Number]
    Example output: TS09EZ4521
    
    This mimics what an ANPR camera would return after reading a real plate.
    In a real system, this plate would then be looked up in the database
    to find the registered user and their vehicle details.
    """
    # Pick a random state
    state_code = random.choice(list(STATE_CODES.keys()))

    # Pick district number (zero-padded to 2 digits)
    low, high = DISTRICT_RANGES[state_code]
    district_num = random.randint(low, high)
    district_str = f"{district_num:02d}"

    # Generate 2-letter series (A-Z, A-Z — skip I and O to avoid confusion)
    safe_letters = [c for c in string.ascii_uppercase if c not in ('I', 'O')]
    series = random.choice(safe_letters) + random.choice(safe_letters)

    # Generate 4-digit number (1000–9999)
    number = random.randint(1000, 9999)

    plate = f"{state_code}{district_str}{series}{number}"
    return plate


def simulate_rfid_scan(registered_plates: list = None) -> dict:
    """
    Simulate an RFID tag scan at the entry gate.
    
    Real behavior:
      - RFID reader powers the tag via radio waves
      - Tag broadcasts its stored UID (mapped to a plate number in DB)
      - Reader captures UID → system looks up the vehicle
    
    In simulation:
      - 70% chance the plate is "registered" (in the registered_plates list)
      - 30% chance it's a new/unknown visitor vehicle
    
    Returns a dict with plate number, scan confidence, and timestamp.
    """
    # If we have a list of registered plates, sometimes pick one of those
    if registered_plates and random.random() < 0.7:
        plate = random.choice(registered_plates)
        is_registered = True
    else:
        plate = generate_plate_number()
        is_registered = False

    # Simulate scan confidence score (real RFID: 100%, ANPR OCR: 85-99%)
    confidence = 100.0 if is_registered else random.uniform(85.0, 99.5)

    scan_result = {
        "sensor_type": "RFID_ANPR",
        "sensor_id": "ANPR_GATE_CAM_01",
        "vehicle_plate": plate,
        "is_registered": is_registered,
        "scan_confidence_pct": round(confidence, 1),
        "state_code": plate[:2],
        "state_name": STATE_CODES.get(plate[:2], "Unknown"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "raw_reading": f"PLATE_DETECTED: {plate} (confidence: {round(confidence,1)}%)"
    }

    return scan_result


def validate_plate_format(plate: str) -> bool:
    """
    Validate that a plate string matches the Indian format.
    Basic check: starts with 2 letters, then 2 digits, then 2 letters, then 4 digits.
    """
    if len(plate) != 10:
        return False
    return (plate[:2].isalpha() and
            plate[2:4].isdigit() and
            plate[4:6].isalpha() and
            plate[6:].isdigit())
