from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

BASE_LAT = 40.7128
BASE_LON = -74.0060

FAULT_CODES = ["P0300", "P0420", "P0171", "C0035"]

@dataclass
class VehicleState:
    vehicle_id: str
    lat: float
    lon: float
    speed_kmh: float
    heading_deg: float
    battery_soc: float
    engine_rpm: int
    fuel_level_pct: float
    diagnostic_code: str
    timestamp: datetime

class VehicleSimulator:
    """One virtual vehicle that updates GPS, speed, battery, and diagnostics."""

    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id
        self.lat = BASE_LAT + random.uniform(-0.01, 0.01)
        self.lon = BASE_LON + random.uniform(-0.01, 0.01)
        self.speed_kmh = random.uniform(10, 40)
        self.heading_deg = random.uniform(0, 360)
        self.battery_soc = random.uniform(0.6, 1.0)
        self.fuel_level_pct = random.uniform(40, 100)
        self.diagnostic_code = "OK"
        self._prev_code = "OK"

    def tick(self, dt_seconds: float = 2.0) -> VehicleState:
        """Advance simulation by dt_seconds and return the new state."""
        # 1) occasional heading change (wandering)
        self.heading_deg = (self.heading_deg + random.uniform(-25, 25)) % 360

        # 2) random speed changes
        self.speed_kmh = max(0.0, min(80.0, self.speed_kmh + random.uniform(-8, 8)))
        
        # 3) move on a rough lat/lon approximation
        #    (good enough for a demo; not survey-grade GPS math)
        distance_km = (self.speed_kmh * dt_seconds) / 3600.0
        heading_rad = math.radians(self.heading_deg)
        self.lat += (distance_km / 111.0) * math.cos(heading_rad)
        self.lon += (distance_km / (111.0 * math.cos(math.radians(self.lat)))) * math.sin(
            heading_rad
        )

        # 4) battery drains a bit every tick; more at higher speed
        base_drain = 0.0002
        speed_factor = (self.speed_kmh / 80.0) * 0.0005
        self.battery_soc = max(0.0, self.battery_soc - base_drain - speed_factor)

        # 5) rpm roughly tracks speed
        self.engine_rpm = int(800 + self.speed_kmh * 35 + random.uniform(-100, 100))

        # 6) tiny fuel drain
        self.fuel_level_pct = max(0.0, self.fuel_level_pct - 0.01)

        # 7) rare diagnostic fault
        self._prev_code = self.diagnostic_code
        if self.diagnostic_code == "OK" and random.random() < 0.02:
            self.diagnostic_code = random.choice(FAULT_CODES)
        elif self.diagnostic_code != "OK" and random.random() < 0.3:
            self.diagnostic_code = "OK"  # clears sometimes

        return VehicleState(
            vehicle_id=self.vehicle_id,
            lat=round(self.lat, 6),
            lon=round(self.lon, 6),
            speed_kmh=round(self.speed_kmh, 1),
            heading_deg=round(self.heading_deg, 1),
            battery_soc=round(self.battery_soc, 3),
            engine_rpm=max(0, self.engine_rpm),
            fuel_level_pct=round(self.fuel_level_pct, 1),
            diagnostic_code=self.diagnostic_code,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    def diagnostic_changed(self) -> bool:
        """True when a fault appears or clears — used by publisher for diagnostics messages."""
        return self.diagnostic_code != self._prev_code

    def to_telemetry_dict(self, state: VehicleState) -> dict:
        return {
            "vehicle_id": state.vehicle_id,
            "timestamp": state.timestamp,
            "lat": state.lat,
            "lon": state.lon,
            "speed_kmh": state.speed_kmh,
            "heading_deg": state.heading_deg,
            "battery_soc": state.battery_soc,
            "engine_rpm": state.engine_rpm,
            "fuel_level_pct": state.fuel_level_pct,
        }


    def to_diagnostics_dict(self, state: VehicleState) -> dict:
        return {
            "vehicle_id": state.vehicle_id,
            "timestamp": state.timestamp,
            "diagnostic_code": state.diagnostic_code,
        }


def create_fleet(n: int = 5) -> list[VehicleSimulator]:
    return [VehicleSimulator(f"vehicle-{i:02d}") for i in range(1, n + 1)]