# 🅿 Smart Parking Management System
### Using IoT Sensors and Data Analytics

---

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

Browser opens automatically at **http://localhost:5000**

**Default Admin Login:**
| Field    | Value              |
|----------|--------------------|
| Email    | admin@parking.com  |
| Password | Admin@1234         |

---

## Demo Flow (for Panel Presentation)

1. **Login** as admin → lands on Live Dashboard
2. Click **"🚗 Simulate Arrival"** → watch a slot turn RED, sensor feed updates, session timer starts
3. Click **"⚡ Auto Fill (3)"** → three vehicles arrive simultaneously
4. Click **"Exit & Bill"** on any active session → bill receipt pops up instantly
5. Click **"🚦 Simulate Exit"** → oldest session exits, slot turns GREEN
6. Open a **second browser tab** → login as a regular User (register first) → see the same slot map update live in real time
7. Visit **Analytics** tab → occupancy trend, revenue chart, peak hour bar chart all update as more sessions run

---

## Project Architecture

```
[Vehicle Arrives]
       ↓
[IR Gate Sensor] ──────── beam broken → entry event logged
       ↓
[RFID/ANPR Camera] ─────── plate detected (e.g. TS09EZ4521)
       ↓
[Slot Allocation Engine] ── nearest free slot assigned (first-fit)
       ↓
[Session Manager] ─────── entry_time recorded, timer starts
       ↓
[Ultrasonic Sensor] ─────── distance < 10cm → confirms OCCUPIED
       ↓
[Live Dashboard] ──────── slot turns RED, timer ticks every second
       ↓
   (vehicle exits?)
    NO → slot stays red, timer keeps running
    YES → [Billing Engine] → fee calculated → slot turns GREEN
       ↓
[Analytics Module] ─────── occupancy %, peak hours, revenue updated
```

---

## How the Sensors Really Work
*(Ready-made answers for your viva voce)*

### 1. Ultrasonic Sensor (HC-SR04) — one per parking slot
**Real principle:** The HC-SR04 sends a burst of ultrasonic sound at 40 kHz and measures how long it takes for the echo to bounce back from an object. The microcontroller converts this time to distance using the formula:

```
distance (cm) = (echo_time_µs × speed_of_sound) / 2
speed of sound ≈ 0.0343 cm/µs at room temperature
Divide by 2 because sound travels TO the object and BACK
```

If the measured distance is **< 10 cm** → a vehicle is directly below the sensor (mounted on ceiling/post) → slot is **OCCUPIED**. If distance is **> 200 cm** → empty floor → slot is **FREE**.

**In this simulation:** We generate a fake echo time mathematically — if occupied, echo time corresponds to ~7 cm; if free, ~300 cm. The same formula is applied. The physics is real; only the hardware pulse is replaced by Python code.

---

### 2. IR Proximity Sensor (Gate Sensor)
**Real principle:** Two components — an **IR emitter** that continuously broadcasts invisible infrared light, and an **IR receiver** on the opposite side. When a vehicle drives through the gate, its body **breaks the IR beam**. The receiver detects the loss of signal (goes from HIGH to LOW) and sends an interrupt signal to the controller.

Response time: ~1 ms. No moving parts. Works in all lighting conditions.

**In this simulation:** We model the "beam broken" event as a Python function that fires when a vehicle arrival or exit action is triggered, and logs the event with a timestamp — exactly what a real microcontroller would send.

---

### 3. RFID / ANPR Camera (Vehicle Identification)
**Real RFID principle:** Each registered vehicle has a **passive RFID tag** on its windscreen. The reader at the gate emits radio waves (~13.56 MHz). The tag absorbs this energy, powers up, and broadcasts its unique UID. The reader captures the UID and looks it up in the database to find the vehicle owner.

**Real ANPR principle:** A camera captures the vehicle's number plate. Computer vision (OCR using YOLO + Tesseract or dedicated LPR chips) reads the plate characters from the image and matches them against a database.

**In this simulation:** We skip the image capture and OCR steps, and directly generate a realistic Indian vehicle registration plate in the correct format (`[State][District][Series][Number]`, e.g. `TS09EZ4521`). This is what the ANPR system would *output* after successfully reading a plate.

---

## Project File Structure

```
smart_parking_system/
├── sensors/
│   ├── ultrasonic_sim.py   ← HC-SR04 distance formula simulation
│   ├── ir_sim.py           ← IR gate beam-break simulation
│   └── rfid_sim.py         ← Indian number plate generator
├── core/
│   ├── slot_manager.py     ← Slot state, first-fit allocation
│   ├── session_manager.py  ← Entry/exit tracking, timer, sensor logging
│   └── billing_engine.py   ← Fee calculation (₹20 first hr + ₹10/hr)
├── analytics/
│   └── analytics_engine.py ← Occupancy trend, peak hours, revenue, prediction
├── auth/
│   └── auth_manager.py     ← Registration, login, password hashing, roles
├── database/
│   └── db_setup.py         ← SQLite schema (5 tables), slot seed, admin seed
├── dashboard/
│   ├── app.py              ← Flask server, all routes, simulation endpoints
│   ├── templates/          ← HTML pages (Jinja2)
│   └── static/             ← CSS + JS (dark theme, live polling)
├── main.py                 ← Entry point (run this!)
├── requirements.txt
└── README.md
```

---

## Database Tables

| Table         | Purpose                                               |
|---------------|-------------------------------------------------------|
| `users`       | Registered users (admin + regular), hashed passwords  |
| `slots`       | 16 parking slots with zone and current status         |
| `sessions`    | Each vehicle's parking session (entry → exit)         |
| `bills`       | Bills generated for completed sessions                |
| `sensor_logs` | All sensor readings (powers the live feed panel)      |

---

## Pricing Logic

| Duration       | Calculation                  | Total  |
|----------------|------------------------------|--------|
| 0–60 min       | First hour flat rate         | ₹20    |
| 61–120 min     | ₹20 + 1×₹10                 | ₹30    |
| 121–180 min    | ₹20 + 2×₹10                 | ₹40    |
| 181–240 min    | ₹20 + 3×₹10                 | ₹50    |

Partial hours are **rounded up** (e.g. 1h 01m = 2 hours billed = ₹30).

---

## Role-Based Access

| Feature                          | Regular User | Admin |
|----------------------------------|:------------:|:-----:|
| View live slot map               | ✅           | ✅    |
| Book/reserve a slot              | ✅           | ✅    |
| View own session history         | ✅           | ✅    |
| Simulate vehicle arrival         | —            | ✅    |
| View ALL active sessions         | —            | ✅    |
| Analytics & revenue charts       | —            | ✅    |
| Manage users                     | —            | ✅    |
| Override slot status             | —            | ✅    |

Routes are protected **server-side** — typing an admin URL directly will redirect a regular user to their dashboard.

---

## Honest Disclaimer (Important for Viva)

> This project **simulates** IoT sensors in software. No physical hardware (Arduino, Raspberry Pi, ultrasonic sensors, IR sensors, or RFID readers) is connected. The sensor logic follows the real mathematical and physical behavior of each sensor type (the distance formula for HC-SR04, the beam-break principle for IR, the plate-read output for ANPR). This is standard and accepted practice for software-only academic projects.

---

## Predictive Analytics (v20 addition)

In addition to the "most frequent entry hour" heuristic, the system now includes a genuine
**linear regression model** (`analytics_engine.predict_next_hour_occupancy()`) that fits a
least-squares line over the last 12 hourly occupancy readings and extrapolates one hour ahead.
It returns the predicted occupancy %, the trend direction (rising/falling/stable), and the
slope — a real statistical forecast, not just a historical readout. Exposed via
`GET /api/predict_occupancy` and shown live on the Analytics tab.

---

## Security Hardening (v20 addition)

- **Login rate limiting**: after 5 failed login attempts for the same email within 5 minutes,
  further attempts are blocked temporarily (in-memory limiter in `dashboard/app.py`).
- **Security headers**: every response now sets `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: SAMEORIGIN`, and `Referrer-Policy: strict-origin-when-cross-origin`.
- All database queries use **parameterized SQL** (`?` placeholders), so the app is not
  vulnerable to basic SQL injection.
- Passwords are stored hashed (see `auth/auth_manager.py`), never in plaintext.

---

## Automated Tests (v20 addition)

Unit tests were added under `tests/` covering the two most safety-critical modules —
billing calculation and vehicle-to-zone allocation — since incorrect logic there would
directly mean wrong charges or wrong slot assignment.

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## Future Scope

- Integrate real hardware (ESP32/Arduino + HC-SR04 ultrasonic sensor + IR beam sensor +
  RFID/ANPR camera) to replace the current software-modeled sensor layer with live
  physical input, using the same data format/interfaces already defined in `sensors/`.
- Migrate from SQLite to PostgreSQL for multi-location, concurrent-write scalability.
- Integrate a real payment gateway (Razorpay/UPI) in place of the simulated payment flow.
- Extend the linear regression occupancy model to a seasonal/day-of-week-aware model
  (e.g. weighted moving average or a small ARIMA model) as more historical data accumulates.
- Add mobile push notifications for "slot about to expire" and "zone full" alerts.

---

## Requirements

- Python 3.8 or higher
- Windows 10 / Linux / macOS
- No internet connection required during demo
- No external hardware

```bash
pip install -r requirements.txt
python main.py
```
