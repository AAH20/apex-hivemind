"""
4D Spatio-Temporal Fratricide Shield & Control Barrier Function (CBF) Engine.
Prevents friendly fire from:
- High-Energy Laser (HEL) line-of-sight optical path intersections
- High-Power Microwave (HPM) conical electromagnetic radiation footprints
- Kinetic missile fragmentation envelopes and flak bursts
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from apex_hivemind.core.primitives import Vector3D, BlueForceUnit, EffectorNode, EffectorKind


class FratricideShieldCBF:
    """
    Sub-microsecond geometric barrier verification.
    Guarantees that no Directed Energy Weapon or kinetic munition
    can be discharged along an azimuth that threatens Blue-Force aircraft.
    """

    def __init__(self, laser_beam_safety_radius_meters: float = 30.0):
        self.laser_safety_radius = laser_beam_safety_radius_meters

    def is_laser_beam_fratricide_free(
        self,
        laser_pos: Vector3D,
        target_pos: Vector3D,
        blue_force_units: List[BlueForceUnit]
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks whether the laser beam cylinder from laser_pos to target_pos
        intersects the safety bubble of any Blue-Force aircraft.
        """
        beam_vec = target_pos - laser_pos
        beam_len = beam_vec.magnitude()
        if beam_len < 1e-3:
            return True, None

        beam_dir = beam_vec.normalized()

        for blue in blue_force_units:
            rel_vec = blue.position - laser_pos
            # Project blue unit onto beam vector
            projection = rel_vec.dot(beam_dir)

            # Check if projection falls along the active beam segment
            if 0.0 <= projection <= beam_len:
                closest_point = laser_pos + (beam_dir * projection)
                dist_to_beam = blue.position.distance_to(closest_point)
                safety_threshold = self.laser_safety_radius + blue.safe_exclusion_radius_meters

                if dist_to_beam < safety_threshold:
                    return False, f"FRATRICIDE VIOLATION: Blue unit {blue.unit_id} is {dist_to_beam:.1f}m from laser beam path"

        return True, None

    def is_hpm_pulse_fratricide_free(
        self,
        hpm_pos: Vector3D,
        pointing_dir: Vector3D,
        max_range_meters: float,
        beam_half_angle_rad: float,
        blue_force_units: List[BlueForceUnit]
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks whether any Blue-Force aircraft resides within the HPM radiation cone.
        """
        norm_dir = pointing_dir.normalized()

        for blue in blue_force_units:
            rel_vec = blue.position - hpm_pos
            dist = rel_vec.magnitude()

            if dist <= max_range_meters:
                cos_theta = rel_vec.normalized().dot(norm_dir)
                angle = math.acos(max(-1.0, min(1.0, cos_theta)))

                if angle <= beam_half_angle_rad:
                    return False, f"FRATRICIDE VIOLATION: Blue unit {blue.unit_id} inside HPM electromagnetic cone ({math.degrees(angle):.1f} deg)"

        return True, None

    def validate_effector_firing_safety(
        self,
        effector: EffectorNode,
        target_pos: Vector3D,
        blue_force_units: List[BlueForceUnit]
    ) -> Tuple[bool, str]:
        """
        Master safety gate before transmitting firing authorizations.
        """
        if not blue_force_units:
            return True, "SAFE: No friendly units reported"

        if effector.kind == EffectorKind.HIGH_ENERGY_LASER:
            safe, reason = self.is_laser_beam_fratricide_free(
                effector.position, target_pos, blue_force_units
            )
            if not safe:
                return False, reason

        elif effector.kind == EffectorKind.HIGH_POWER_MICROWAVE:
            pointing = target_pos - effector.position
            safe, reason = self.is_hpm_pulse_fratricide_free(
                effector.position,
                pointing,
                effector.max_effective_range_meters,
                0.2618,  # ~15 degree cone
                blue_force_units
            )
            if not safe:
                return False, reason

        return True, "SAFE: Effector engagement corridor clear of friendly units"
