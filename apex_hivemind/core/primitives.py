"""
Mathematical and Operational Primitives for Apex-HiveMind.
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class Vector3D:
    x: float
    y: float
    z: float

    def __add__(self, other: Vector3D) -> Vector3D:
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3D) -> Vector3D:
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vector3D:
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vector3D:
        return self * scalar

    def magnitude(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def dot(self, other: Vector3D) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vector3D) -> Vector3D:
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x
        )

    def distance_to(self, other: Vector3D) -> float:
        return (self - other).magnitude()

    def normalized(self) -> Vector3D:
        mag = self.magnitude()
        if mag < 1e-9:
            return Vector3D(0.0, 0.0, 0.0)
        return Vector3D(self.x / mag, self.y / mag, self.z / mag)


class ThreatClassification(str, Enum):
    FPV_SWARM_DRONE = "FPV_SWARM_DRONE"
    LOITERING_MUNITION = "LOITERING_MUNITION"
    CRUISE_MISSILE = "CRUISE_MISSILE"
    BALLISTIC_MISSILE = "BALLISTIC_MISSILE"
    RECON_UAV = "RECON_UAV"
    ELECTRONIC_DECOY = "ELECTRONIC_DECOY"


class EffectorKind(str, Enum):
    HIGH_POWER_MICROWAVE = "HIGH_POWER_MICROWAVE"  # Wide-area EMP cone
    HIGH_ENERGY_LASER = "HIGH_ENERGY_LASER"        # Optical/thermal spot burn
    PRECISION_MISSILE = "PRECISION_MISSILE"        # Kinetic interceptor
    AIRBURST_GUN = "AIRBURST_GUN"                  # Programmable 35mm flak
    BLUE_INTERCEPTOR_SWARM = "BLUE_INTERCEPTOR_SWARM"  # Dogfight air-to-air drone


@dataclass
class ThreatTarget:
    target_id: str
    classification: ThreatClassification
    position: Vector3D
    velocity: Vector3D
    threat_value: float  # Scale 1.0 to 100.0 (e.g. Ballistic=90, Cruise=75, FPV=20)
    radar_cross_section_sqm: float
    confirmed: bool = True
    neutralized: bool = False


@dataclass
class EffectorNode:
    effector_id: str
    kind: EffectorKind
    position: Vector3D
    max_effective_range_meters: float
    min_effective_range_meters: float = 50.0
    slew_rate_rad_s: float = 1.5  # Slew speed limit
    current_pointing_azimuth_rad: float = 0.0
    current_pointing_elevation_rad: float = 0.0
    thermal_saturation_pct: float = 0.0  # 0 to 100% (Lasers)
    capacitor_charge_pct: float = 100.0  # 0 to 100% (HPM)
    ammunition_rounds: int = 10          # Missiles / bursts
    is_operational: bool = True


@dataclass
class BlueForceUnit:
    unit_id: str
    position: Vector3D
    velocity: Vector3D
    safe_exclusion_radius_meters: float = 25.0


@dataclass
class EngagementAllocation:
    effector_id: str
    target_id: str
    effector_kind: EffectorKind
    single_shot_pk: float
    dwell_time_seconds: float = 0.0
    rounds_fired: int = 1
    fratricide_safe: bool = True
    intercept_point: Vector3D = field(default_factory=lambda: Vector3D(0, 0, 0))


@dataclass
class HiveMindCycleReport:
    cycle_index: int
    total_cycle_latency_us: float
    threats_detected: int
    threats_neutralized: int
    surviving_threat_value: float
    active_allocations: List[EngagementAllocation]
    fratricide_violations_prevented: int
    hash_chain_head: str
    phase_latencies_us: Dict[str, float] = field(default_factory=dict)
