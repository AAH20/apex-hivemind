"""
Phase 1: Multi-INT Ingestion & Cognitive RF Sensing.
Ingests multi-spectral feeds: AESA radar, EO/IR, SIGINT/ESM, STANAG 4607, Cursor-on-Target (CoT).
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from apex_hivemind.core.primitives import Vector3D, ThreatClassification, ThreatTarget


@dataclass
class RawSensorContact:
    contact_id: str
    sensor_kind: str  # 'AESA_RADAR', 'EO_IR_OPTIC', 'SIGINT_ESM', 'COFFEE_LINK'
    observed_position: Vector3D
    observed_velocity: Vector3D
    radar_cross_section_sqm: float
    signal_to_noise_ratio_db: float
    emitter_frequency_mhz: Optional[float] = None
    timestamp_ns: int = field(default_factory=time.perf_counter_ns)


class MultiINTIngestionEngine:
    """
    Ingests and normalizes disparate sensor streams into canonical Cartesian coordinates.
    Filters out thermal background clutter and false radar returns.
    """

    def __init__(self, min_snr_threshold_db: float = 3.0):
        self.min_snr = min_snr_threshold_db

    def parse_aesa_radar_detection(
        self,
        radar_id: str,
        slant_range_m: float,
        azimuth_deg: float,
        elevation_deg: float,
        doppler_velocity_mps: float,
        rcs_sqm: float,
        snr_db: float
    ) -> Optional[RawSensorContact]:
        """Converts spherical radar coordinates to Cartesian contact."""
        if snr_db < self.min_snr:
            return None  # Clutter rejection

        az_rad = math.radians(azimuth_deg)
        el_rad = math.radians(elevation_deg)

        r_xy = slant_range_m * math.cos(el_rad)
        x = r_xy * math.cos(az_rad)
        y = r_xy * math.sin(az_rad)
        z = slant_range_m * math.sin(el_rad)

        vel_dir = Vector3D(x, y, z).normalized()
        vel = vel_dir * doppler_velocity_mps

        return RawSensorContact(
            contact_id=f"RADAR-{radar_id}-{int(time.perf_counter_ns() % 1000000)}",
            sensor_kind="AESA_RADAR",
            observed_position=Vector3D(x, y, z),
            observed_velocity=vel,
            radar_cross_section_sqm=rcs_sqm,
            signal_to_noise_ratio_db=snr_db
        )

    def parse_sigint_emitter(
        self,
        emitter_id: str,
        bearing_azimuth_deg: float,
        bearing_elevation_deg: float,
        estimated_distance_m: float,
        frequency_mhz: float,
        pulse_repetition_interval_us: float
    ) -> RawSensorContact:
        """Processes RF electronic warfare / telemetry emitter intercepts."""
        az_rad = math.radians(bearing_azimuth_deg)
        el_rad = math.radians(bearing_elevation_deg)

        r_xy = estimated_distance_m * math.cos(el_rad)
        x = r_xy * math.cos(az_rad)
        y = r_xy * math.sin(az_rad)
        z = estimated_distance_m * math.sin(el_rad)

        return RawSensorContact(
            contact_id=f"SIGINT-{emitter_id}",
            sensor_kind="SIGINT_ESM",
            observed_position=Vector3D(x, y, z),
            observed_velocity=Vector3D(0.0, 0.0, 0.0),
            radar_cross_section_sqm=0.0,
            signal_to_noise_ratio_db=15.0,
            emitter_frequency_mhz=frequency_mhz
        )
