"""
Directed Energy Weapons (DEW) Scheduling & Physics Engine for Apex-HiveMind.
Models:
- High-Energy Laser (HEL) thermal bloom, heat accumulation & atmospheric extinction
- High-Power Microwave (HPM) capacitor bank discharge & pulse duty cycle
- Electro-optical gimbal slew dynamics and angular acceleration
Zero external dependencies. Pure Python standard library.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from apex_hivemind.core.primitives import Vector3D, EffectorNode, ThreatTarget, EffectorKind


class DirectedEnergyScheduler:
    """
    Solves thermal bloom constraints, slew dynamics, and capacitor reloads
    for continuous-wave High-Energy Lasers (HEL) and pulsed High-Power Microwave (HPM) weapons.
    """

    def __init__(
        self,
        laser_power_kw: float = 50.0,
        atmospheric_extinction_coeff: float = 0.00015,  # per meter (clear combat air)
        critical_fluence_kj_cm2: float = 8.0,          # Kill fluence for UAV casing
        hpm_discharge_per_pulse_pct: float = 20.0,
        hpm_recharge_rate_pct_s: float = 15.0,
        laser_cooldown_rate_pct_s: float = 12.0
    ):
        self.laser_power_kw = laser_power_kw
        self.alpha_extinction = atmospheric_extinction_coeff
        self.critical_fluence = critical_fluence_kj_cm2
        self.hpm_discharge = hpm_discharge_per_pulse_pct
        self.hpm_recharge = hpm_recharge_rate_pct_s
        self.laser_cooldown = laser_cooldown_rate_pct_s

    def compute_slew_time(
        self,
        effector: EffectorNode,
        target_pos: Vector3D
    ) -> float:
        """
        Calculates time required for optical turret/emitter to slew to target line-of-sight.
        """
        rel_vec = target_pos - effector.position
        dist = rel_vec.magnitude()
        if dist < 1e-3:
            return 0.0

        # Target azimuth and elevation
        target_az = math.atan2(rel_vec.y, rel_vec.x)
        target_el = math.asin(max(-1.0, min(1.0, rel_vec.z / dist)))

        delta_az = abs(target_az - effector.current_pointing_azimuth_rad)
        delta_el = abs(target_el - effector.current_pointing_elevation_rad)
        # Account for 2*pi azimuth wrapping
        if delta_az > math.pi:
            delta_az = 2.0 * math.pi - delta_az

        total_angular_slew = math.sqrt(delta_az * delta_az + delta_el * delta_el)
        return total_angular_slew / max(effector.slew_rate_rad_s, 0.1)

    def compute_laser_required_dwell(
        self,
        effector: EffectorNode,
        target: ThreatTarget
    ) -> float:
        """
        Calculates dwell time required to breach target structure or burn seeker head.
        Accounts for Beer-Lambert atmospheric attenuation: P_rx = P_0 * exp(-alpha * d).
        """
        dist = effector.position.distance_to(target.position)
        if dist > effector.max_effective_range_meters or dist < effector.min_effective_range_meters:
            return 999.0  # Out of range

        attenuation = math.exp(-self.alpha_extinction * dist)
        received_power_kw = self.laser_power_kw * attenuation

        # Target toughness factor by classification
        toughness_scalar = 1.0
        if target.classification.value in ("CRUISE_MISSILE", "BALLISTIC_MISSILE"):
            toughness_scalar = 2.5  # Hardened titanium/composite airframe

        # Dwell time = Fluence / Power density
        required_dwell_s = (self.critical_fluence * toughness_scalar * 10.0) / max(received_power_kw, 1.0)
        return max(0.2, min(required_dwell_s, 6.0))

    def evaluate_hpm_pulse_feasibility(
        self,
        effector: EffectorNode,
        target_cluster: List[ThreatTarget],
        beam_half_angle_rad: float = 0.2618  # ~15 degrees cone
    ) -> Tuple[bool, List[str]]:
        """
        Determines whether HPM can pulse fire and lists targets caught in its radiation footprint.
        """
        if effector.capacitor_charge_pct < self.hpm_discharge:
            return False, []  # Capacitor not sufficiently charged

        targets_in_cone: List[str] = []
        pointing_dir = Vector3D(
            math.cos(effector.current_pointing_azimuth_rad) * math.cos(effector.current_pointing_elevation_rad),
            math.sin(effector.current_pointing_azimuth_rad) * math.cos(effector.current_pointing_elevation_rad),
            math.sin(effector.current_pointing_elevation_rad)
        ).normalized()

        for tgt in target_cluster:
            rel = tgt.position - effector.position
            dist = rel.magnitude()
            if dist <= effector.max_effective_range_meters and dist >= effector.min_effective_range_meters:
                cos_angle = rel.normalized().dot(pointing_dir)
                angle = math.acos(max(-1.0, min(1.0, cos_angle)))
                if angle <= beam_half_angle_rad:
                    targets_in_cone.append(tgt.target_id)

        return len(targets_in_cone) > 0, targets_in_cone

    def update_physics_step(
        self,
        effectors: List[EffectorNode],
        active_dwells: Dict[str, float],
        active_hpm_pulses: Set[str],
        dt: float = 0.05
    ) -> None:
        """
        Updates thermal saturation and capacitor recharges across all DEW systems.
        """
        for eff in effectors:
            if eff.kind == EffectorKind.HIGH_ENERGY_LASER:
                if eff.effector_id in active_dwells:
                    # Laser firing accumulates heat
                    heat_gain = 8.0 * dt * 10.0  # % per second
                    eff.thermal_saturation_pct = min(100.0, eff.thermal_saturation_pct + heat_gain)
                else:
                    # Laser cooling
                    eff.thermal_saturation_pct = max(0.0, eff.thermal_saturation_pct - (self.laser_cooldown * dt))

            elif eff.kind == EffectorKind.HIGH_POWER_MICROWAVE:
                if eff.effector_id in active_hpm_pulses:
                    eff.capacitor_charge_pct = max(0.0, eff.capacitor_charge_pct - self.hpm_discharge)
                else:
                    eff.capacitor_charge_pct = min(100.0, eff.capacitor_charge_pct + (self.hpm_recharge * dt))
