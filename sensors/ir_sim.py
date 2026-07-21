"""
Module 1: IR Proximity Sensor Simulation (Gate Entry/Exit)
==========================================================
REAL SENSOR EXPLANATION (for viva):
  An IR (Infrared) proximity sensor at a gate consists of two parts:
    - IR Emitter: continuously sends invisible infrared light across the lane
    - IR Receiver: sits on the opposite side and detects the light beam

  When a vehicle passes through the gate, its body BREAKS the IR beam.
  The receiver stops detecting infrared → sends a HIGH signal to the controller.
  This event triggers either an ENTRY or EXIT log depending on which gate.

  Real sensors like TCRT5000 or E18-D80NK work this way.
  Response time: ~1 ms (very fast, no delay).

  In this simulation: we model the beam-break event as a boolean trigger
  that fires when a vehicle "arrive" or "exit" action is called.
"""

import time
import random


class IRGateSensor:
    """
    Simulates an IR break-beam sensor installed at a parking gate.
    
    Each gate (ENTRY or EXIT) has one IR sensor.
    When a vehicle passes, the beam is broken → event is logged.
    """

    def __init__(self, gate_id: str, gate_type: str):
        """
        Initialize a gate IR sensor.
        
        gate_id  : Unique identifier, e.g. "GATE_ENTRY_A" or "GATE_EXIT_A"
        gate_type: "ENTRY" or "EXIT"
        """
        self.gate_id = gate_id
        self.gate_type = gate_type  # "ENTRY" or "EXIT"
        self.beam_active = True     # Beam is ON (unbroken) by default
        self.last_event = None      # Stores the last trigger event

    def trigger_vehicle_detection(self) -> dict:
        """
        Simulate a vehicle breaking the IR beam at the gate.
        
        Real behavior:
          1. Beam is initially active (IR light flowing, receiver is HIGH)
          2. Vehicle enters → body blocks IR beam → receiver drops to LOW
          3. Controller reads the LOW signal → logs the event
          4. Vehicle fully passes → beam is restored → receiver goes HIGH again
        
        Returns: an event dictionary with gate info and timestamp,
                 like what a real microcontroller would send via serial/MQTT.
        """
        # Step 1: Beam is broken (vehicle detected)
        self.beam_active = False

        # Simulate brief detection window (50–200 ms in real hardware)
        detection_duration_ms = random.randint(50, 200)

        # Build the event payload
        event = {
            "sensor_type": "IR_PROXIMITY_GATE",
            "sensor_id": self.gate_id,
            "gate_type": self.gate_type,
            "beam_broken": True,
            "beam_active": self.beam_active,
            "detection_duration_ms": detection_duration_ms,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "raw_reading": "BEAM_BROKEN — VEHICLE DETECTED"
        }

        # Store as last event
        self.last_event = event

        # Step 2: Restore beam (vehicle has fully passed through)
        self.beam_active = True

        return event

    def check_beam_status(self) -> dict:
        """
        Read the current beam status (is the IR light path clear?).
        
        Returns BEAM_CLEAR if no vehicle is blocking the gate,
        or BEAM_BROKEN if something is in the way (e.g. car stopped at gate).
        """
        return {
            "sensor_id": self.gate_id,
            "beam_active": self.beam_active,
            "status": "BEAM_CLEAR" if self.beam_active else "BEAM_BROKEN",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }


# Create the two gate sensors for the parking lot
# Zone A gate (slots 1-8) and Zone B gate (slots 9-16)
entry_gate_A = IRGateSensor("GATE_ENTRY_A", "ENTRY")
exit_gate_A  = IRGateSensor("GATE_EXIT_A",  "EXIT")
entry_gate_B = IRGateSensor("GATE_ENTRY_B", "ENTRY")
exit_gate_B  = IRGateSensor("GATE_EXIT_B",  "EXIT")


def trigger_entry_event(zone: str = "A") -> dict:
    """
    Trigger an entry event at the specified zone gate.
    Returns the IR sensor event data for logging.
    """
    if zone == "A":
        return entry_gate_A.trigger_vehicle_detection()
    else:
        return entry_gate_B.trigger_vehicle_detection()


def trigger_exit_event(zone: str = "A") -> dict:
    """
    Trigger an exit event at the specified zone gate.
    Returns the IR sensor event data for logging.
    """
    if zone == "A":
        return exit_gate_A.trigger_vehicle_detection()
    else:
        return exit_gate_B.trigger_vehicle_detection()
